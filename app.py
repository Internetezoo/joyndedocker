import os
import time
import threading
from flask import Flask, jsonify, send_file
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# Állapot tárolása
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
            log_msg("Böngésző indítása (Shadow DOM + Low RAM)...")
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process"
            ])
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="de-DE"
            )
            
            page = context.new_page()
            page.set_viewport_size({"width": 1280, "height": 720})

            # --- RAM SPÓROLÁS: Képek és felesleg blokkolása ---
            def block_heavy(route):
                if route.request.resource_type in ["image", "font", "media"]:
                    route.abort()
                else:
                    route.continue_()
            page.route("**/*", block_heavy)

            # --- M3U8 ELFOGÁSA ---
            def handle_response(response):
                if "playlist" in response.url and response.request.method == "POST":
                    if response.status == 200:
                        try:
                            url = response.json().get("manifestUrl")
                            if url:
                                found_data["m3u8"] = url
                                log_msg("!!! SIKER: M3U8 ELKAPVA !!!")
                        except: pass

            page.on("response", handle_response)
            
            log_msg(f"Navigálás: {target_url}")
            page.goto(target_url, wait_until="commit", timeout=60000)
            
            # Várunk, hogy a Shadow DOM betöltsön
            time.sleep(12)
            page.screenshot(path="debug.png")
            log_msg("Screenshot mentve (ezt nézd meg a /screenshot oldalon).")

            # --- SÜTI ELFOGADÁS (SHADOW DOM BIZTOS) ---
            log_msg("Süti ablak kezelése...")
            try:
                # 1. módszer: Playwright shadow selector
                cookie_btn = page.locator("cmp-banner >> button:has-text('Akzeptieren'), cmp-banner >> button.button--primary").first
                if cookie_btn.is_visible():
                    cookie_btn.click(timeout=5000)
                    log_msg("Süti gomb megnyomva (Selector).")
                else:
                    # 2. módszer: Közvetlen JavaScript injekció a Shadow Root-ba
                    page.evaluate("""
                        const banner = document.querySelector('cmp-banner');
                        if (banner && banner.shadowRoot) {
                            const btn = banner.shadowRoot.querySelector('button.button--primary') || 
                                        banner.shadowRoot.querySelector('button');
                            if (btn) btn.click();
                        }
                    """)
                    log_msg("Süti gomb megnyomva (JS injection).")
            except Exception as e:
                log_msg(f"Süti hiba: {str(e)[:50]}")

            # --- PLAY GOMB ---
            time.sleep(5)
            try:
                play_btn = page.locator("[data-testid='play-button']").first
                if play_btn.is_visible():
                    play_btn.click(force=True)
                    log_msg("Play gomb megnyomva!")
                else:
                    # Ha nem látja a gombot, kattintunk egyet középre "vakon"
                    page.mouse.click(640, 360)
                    log_msg("Vak kattintás középre...")
            except:
                pass

            # Várakozás a válaszra (max 60 mp)
            start_wait = time.time()
            while not found_data["m3u8"] and (time.time() - start_wait < 60):
                time.sleep(5)

            if not found_data["m3u8"]:
                page.screenshot(path="debug.png")
                log_msg("Nem jött meg az M3U8 időben.")

            browser.close()
            found_data["status"] = "Completed" if found_data["m3u8"] else "Failed"

        except Exception as e:
            log_msg(f"Végzetes hiba: {str(e)}")
            found_data["status"] = "Error"
            found_data["last_error"] = str(e)

# --- FLASK ROUTES ---

@app.route('/')
def index():
    return jsonify(found_data), 200

@app.route('/start')
def start():
    if found_data["status"] != "Running":
        found_data["logs"] = []
        threading.Thread(target=run_scraper).start()
        return "Folyamat elindítva...", 202
    return "Már fut egy folyamat.", 200

@app.route('/screenshot')
def screenshot():
    if os.path.exists("debug.png"):
        return send_file("debug.png", mimetype='image/png')
    return "Nincs kép.", 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)
