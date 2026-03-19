import os
import time
import threading
from flask import Flask, jsonify, send_file, request
from playwright.sync_api import sync_playwright

app = Flask(__name__)
# JSON szép megjelenítése a böngészőben
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
app.config['JSON_AS_ASCII'] = False

# Állapot tárolása
found_data = {
    "status": "Idle",
    "m3u8": None,
    "video_url": None,
    "last_error": None,
    "logs": []
}

VIDEO_DIR = "videos"
if not os.path.exists(VIDEO_DIR):
    os.makedirs(VIDEO_DIR)

def log_msg(msg):
    timestamp = time.strftime('%H:%M:%S')
    print(f"[*] {timestamp}: {msg}")
    found_data["logs"].append(f"{timestamp}: {msg}")

def run_scraper(base_url):
    global found_data
    found_data["status"] = "Running"
    found_data["m3u8"] = None
    found_data["video_url"] = None
    target_url = "https://www.joyn.de/play/serien/die-waltons/1-1-das-findelkind"
    
    # Takarítás
    for f in os.listdir(VIDEO_DIR):
        try: os.remove(os.path.join(VIDEO_DIR, f))
        except: pass

    with sync_playwright() as p:
        browser = None
        context = None
        try:
            log_msg("Böngésző indítása videóval...")
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"
            ])
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="de-DE",
                record_video_dir=VIDEO_DIR,
                record_video_size={"width": 1280, "height": 720}
            )
            
            page = context.new_page()
            page.set_viewport_size({"width": 1280, "height": 720})

            # M3U8 figyelése
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
            
            time.sleep(12)
            
            # Süti kezelés (Shadow DOM)
            try:
                page.evaluate("""
                    const b = document.querySelector('cmp-banner');
                    if(b && b.shadowRoot) b.shadowRoot.querySelector('button.button--primary')?.click();
                """)
                log_msg("Süti elfogadva.")
            except: pass

            # Videó indítása és 60 mp rögzítés
            time.sleep(5)
            try:
                page.locator("[data-testid='play-button']").first.click(force=True, timeout=5000)
                log_msg("Play megnyomva.")
            except:
                page.mouse.click(640, 360)
                log_msg("Vak kattintás a lejátszóra.")

            log_msg("Rögzítés folyamatban (60 mp)...")
            time.sleep(60) 
            
            # Mentés és Link generálás
            video_file_path = page.video.path()
            video_filename = os.path.basename(video_file_path)
            found_data["video_url"] = f"{base_url}video"
            log_msg(f"Videó kész: {video_filename}")

            context.close()
            browser.close()
            found_data["status"] = "Completed"

        except Exception as e:
            log_msg(f"Hiba: {e}")
            found_data["status"] = "Error"
            found_data["last_error"] = str(e)
            if context: context.close()
            if browser: browser.close()

# --- FLASK VÉGPONTOK ---

@app.route('/')
def index():
    # Szépített, olvasható JSON válasz
    return jsonify(found_data)

@app.route('/start')
def start():
    if found_data["status"] != "Running":
        found_data["logs"] = []
        # Megállapítjuk az aktuális címet a linkhez (pl. https://joyndedocker.onrender.com/)
        base_url = request.host_url
        threading.Thread(target=run_scraper, args=(base_url,)).start()
        return jsonify({"message": "Folyamat elindítva", "check_here": base_url}), 202
    return jsonify({"message": "Már fut egy folyamat"}), 200

@app.route('/video')
def get_video():
    # Megkeressük az egyetlen videófájlt a mappában
    files = os.listdir(VIDEO_DIR)
    if files:
        full_path = os.path.join(VIDEO_DIR, files[0])
        return send_file(full_path, mimetype='video/webm')
    return "Nincs rögzített videó.", 404

@app.route('/screenshot')
def screenshot():
    if os.path.exists("debug.png"):
        return send_file("debug.png", mimetype='image/png')
    return "Nincs kép.", 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)
