import os
import time
import threading
from flask import Flask, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

found_data = {"m3u8": None, "status": "Idle", "last_error": None}

def run_scraper():
    global found_data
    found_data["status"] = "Running"
    target_url = "https://www.joyn.de/play/serien/die-waltons/1-1-das-findelkind"
    
    print("[*] Böngésző indítása (Low-RAM mód)...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True, 
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage", # Fontos Dockerben!
                    "--disable-gpu",           # Spórol a RAM-mal
                    "--js-flags='--max-old-space-size=256'" # Korlátozza a JS memóriaigényét
                ]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                locale="de-DE"
            )
            
            page = context.new_page()
            # Kisebb felbontás = kevesebb RAM
            page.set_viewport_size({"width": 1024, "height": 768})

            def handle_response(response):
                if "playlist" in response.url and response.request.method == "POST":
                    if response.status == 200:
                        try:
                            json_data = response.json()
                            url = json_data.get("manifestUrl")
                            if url:
                                found_data["m3u8"] = url
                                print(f"\n[!!!] SIKER: {url}")
                        except: pass

            page.on("response", handle_response)
            
            print(f"[*] Navigálás: {target_url}")
            page.goto(target_url, wait_until="commit", timeout=90000)

            start_time = time.time()
            while not found_data["m3u8"]:
                elapsed = int(time.time() - start_time)
                
                # Próbálunk kattintani, ha betöltődött valami
                try:
                    # Joyn cookie gomb selector
                    page.click("button[id*='cmp-parent']", timeout=2000) 
                except: pass

                try:
                    page.click("[data-testid='play-button']", timeout=2000)
                except: pass

                if elapsed > 300:
                    found_data["status"] = "Timeout"
                    break
                time.sleep(5)

            browser.close()
            found_data["status"] = "Completed" if found_data["m3u8"] else "Failed"

        except Exception as e:
            print(f"[HIBA]: {str(e)}")
            found_data["status"] = "Error"
            found_data["last_error"] = str(e)

@app.route('/')
def health_check():
    return jsonify(found_data), 200

@app.route('/start')
def start_bot():
    # Csak akkor indítjuk, ha nem fut
    if found_data["status"] not in ["Running"]:
        thread = threading.Thread(target=run_scraper)
        thread.start()
        return "Scraper elindítva a háttérben...", 202
    return "A scraper már fut!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # Threaded=True segít a Flask-nek kezelni a kéréseket a scrapper mellett
    app.run(host='0.0.0.0', port=port, threaded=True)
