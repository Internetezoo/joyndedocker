import os
import time
import threading
from flask import Flask, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# Globális változó az eredmény tárolására
found_data = {"m3u8": None, "status": "Idle", "last_error": None}

def run_scraper():
    global found_data
    found_data["status"] = "Running"
    target_url = "https://www.joyn.de/play/serien/die-waltons/1-1-das-findelkind"
    
    print("[*] Böngésző indítása...")
    with sync_playwright() as p:
        try:
            # Render/Docker specifikus beállítások
            browser = p.chromium.launch(
                headless=True, 
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage",
                    "--mute-audio"
                ]
            )
            
            # Német nyelv és normál User Agent beállítása
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                locale="de-DE"
            )
            
            page = context.new_page()
            page.set_viewport_size({"width": 1280, "height": 720})

            def handle_response(response):
                # Joyn manifest URL keresése a hálózati forgalomban
                if "playlist" in response.url and response.request.method == "POST":
                    if response.status == 200:
                        try:
                            json_data = response.json()
                            url = json_data.get("manifestUrl")
                            if url:
                                found_data["m3u8"] = url
                                print(f"\n[!!!] SIKER: {url}")
                        except:
                            pass

            page.on("response", handle_response)
            
            print(f"[*] Navigálás: {target_url}")
            page.goto(target_url, wait_until="networkidle", timeout=60000)

            start_time = time.time()
            while not found_data["m3u8"]:
                elapsed = int(time.time() - start_time)
                
                # 1. Cookie elfogadása (ha megjelenik)
                try:
                    cookie_btn = page.locator("button.button--primary.button--animated").first
                    if cookie_btn.count() > 0 and cookie_btn.is_visible():
                        cookie_btn.click(force=True, timeout=1000)
                        print(f"[{elapsed}s] Cookie elfogadva.")
                except:
                    pass

                # 2. Play gomb megnyomása
                try:
                    play_btn = page.locator("[data-testid='play-button']").first
                    if play_btn.count() > 0 and play_btn.is_visible():
                        play_btn.click(force=True, timeout=1000)
                        print(f"[{elapsed}s] Play megnyomva.")
                except:
                    pass

                # Timeout 5 perc után
                if elapsed > 300:
                    found_data["status"] = "Timeout"
                    break
                
                time.sleep(2)

            if found_data["m3u8"]:
                found_data["status"] = "Completed"
            
            browser.close()

        except Exception as e:
            print(f"[HIBA]: {str(e)}")
            found_data["status"] = "Error"
            found_data["last_error"] = str(e)

# --- FLASK ROUTES ---

@app.route('/')
def health_check():
    """A Render ezen keresztül ellenőrzi, hogy fut-e az app."""
    return jsonify({
        "message": "Joyn Scraper is alive",
        "current_status": found_data["status"],
        "result": found_data["m3u8"]
    }), 200

@app.route('/start')
def start_bot():
    """Kézi indítás a /start URL-en keresztül."""
    if found_data["status"] != "Running":
        thread = threading.Thread(target=run_scraper)
        thread.start()
        return "Scraper started in background...", 202
    return "Scraper is already running.", 200

if __name__ == "__main__":
    # Render automatikusan adja a PORT környezeti változót
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
