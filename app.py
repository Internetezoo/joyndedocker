import os
import time
import threading
from flask import Flask, jsonify, send_file
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# Globális állapot tárolása
found_data = {
    "m3u8": None, 
    "status": "Idle", 
    "last_error": None, 
    "logs": []
}

def log_msg(msg):
    timestamp = time.strftime('%H:%M:%S')
    print(f"[*] {timestamp}: {msg}")
    found_data["logs"].append(f"{timestamp}: {msg}")

def run_scraper():
    global found_data
    found_data["status"] = "Running"
    found_data["m3u8"] = None
    target_url = "https://www.joyn.de/play/serien/die-waltons/1-1-das-findelkind"
    
    with sync_playwright() as p:
        try:
            log_msg("Böngésző indítása (DRASZTIKUS LOW-RAM mód)...")
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process", # Egyetlen folyamatba kényszerítés (RAM spórolás)
                "--js-flags='--max-old-space-size=128'" # JS memória korlátozása
            ])
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="de-DE"
            )
            
            page = context.new_page()
            # Kisebb felbontás = kisebb memória lábnyom
            page.set_viewport_size({"width": 800, "height": 600})

            # --- ERŐFORRÁS BLOKKOLÁS (A TITOK NYITJA) ---
            def block_heavy_stuff(route):
                # Letiltunk mindent, ami nem elengedhetetlen a manifestUrl-hez
                bad_types = ["image", "font", "stylesheet", "media", "other"]
                if route.request.resource_type in bad_types:
                    route.abort()
                # Letiltjuk a hirdetéseket és követőket is
                elif any(x in route.request.url for x in ["google", "analytics", "doubleclick", "facebook", "adition"]):
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", block_heavy_stuff)

            # --- VÁLASZ FIGYELÉSE ---
            def handle_response(response):
                if "playlist" in response.url and response.request.method == "POST":
                    if response.status == 200:
                        try:
                            url = response.json().get("manifestUrl")
                            if url:
                                found_data["m3u8"] = url
                                log_msg("!!! SIKER: M3U8 ELKAPVA !!!")
                        except:
                            pass

            page.on("response", handle_response)
            
            log_msg(f"Navigálás: {target_url}")
            # Csak a 'commit'-ig várunk, hogy ne fusson ki az időből
            page.goto(target_url, wait_until="commit", timeout=90000)
            
            # Rövid várakozás, hogy a háttérben lefusson a POST kérés
            start_wait = time.time()
            while not found_data["m3u8"] and (time.time() - start_wait < 60):
                # Próbálunk egy "vak" kattintást a képernyő közepére, hátha elindítja a lejátszót
                try:
                    page.mouse.click(400, 300)
                    log_msg("Vak kattintás a lejátszó helyére...")
                except:
                    pass
                time.sleep(10)

            if not found_data["m3u8"]:
                log_msg("Nem érkezett meg a válasz 60 másodperc alatt.")
                page.screenshot(path="debug.png")
            
            browser.close()
            found_data["status"] = "Completed" if found_data["m3u8"] else "Failed"

        except Exception as e:
            log_msg(f"HIBA: {str(e)}")
            found_data["status"] = "Error"
            found_data["last_error"] = str(e)

# --- FLASK VÉGPONTOK ---

@app.route('/')
def health_check():
    return jsonify(found_data), 200

@app.route('/start')
def start_bot():
    if found_data["status"] != "Running":
        found_data["logs"] = []
        threading.Thread(target=run_scraper).start()
        return "Scraper elindítva (Extrém mód)...", 202
    return "Már fut egy folyamat.", 200

@app.route('/screenshot')
def get_screenshot():
    if os.path.exists("debug.png"):
        return send_file("debug.png", mimetype='image/png')
    return "Nincs screenshot (még fut vagy sikerült)", 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)
