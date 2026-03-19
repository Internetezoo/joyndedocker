import asyncio
import os
import sys
import threading
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from playwright.async_api import async_playwright

app = Flask(__name__)

# --- KONFIGURÁCIÓ ---
VIDEO_DIR = os.path.join(os.getcwd(), "videos")
os.makedirs(VIDEO_DIR, exist_ok=True)

# Globális állapotok
logs = []
last_hits = {}
video_files = {}
is_running = False

def dlog(msg):
    """Logolás a konzolba ÉS a webes felületre"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    print(entry)
    sys.stdout.flush()
    logs.append(entry)
    # Csak az utolsó 50 sort tartsuk meg a memóriában
    if len(logs) > 50:
        logs.pop(0)

async def run_scraper_logic(url):
    global is_running
    is_running = True
    hits = []
    
    if url not in last_hits:
        last_hits[url] = []

    async with async_playwright() as p:
        dlog(f"🚀 Böngésző indítása (Headless + Video)... Target: {url}")
        try:
            browser = await p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            
            context = await browser.new_context(
                record_video_dir=VIDEO_DIR,
                viewport={'width': 1280, 'height': 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            
            # Sniffer: minden m3u8 linket elmentünk
            page.on("request", lambda req: (
                hits.append(req.url), 
                last_hits[url].append(req.url),
                dlog(f"🎯 TALÁLAT: {req.url[:60]}...")
            ) if "m3u8" in req.url.lower() else None)

            dlog("📡 Navigálás az oldalra (domcontentloaded)...")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            dlog("⏳ Várakozás a stream indulására (30 mp)...")
            # Megpróbáljuk megnyomni a Play gombot, ha van
            try:
                play_btn = page.locator("button:has-text('Abspielen'), [data-testid='play-button']").first
                if await play_btn.is_visible(timeout=5000):
                    await play_btn.click()
                    dlog("🖱️ Play gomb megnyomva.")
            except:
                pass

            await asyncio.sleep(30) # Ennyi kell a videó rögzítéséhez és a linkekhez
            
            video_path = await page.video.path()
            video_files[url] = os.path.basename(video_path) if video_path else None
            dlog(f"📹 Videó kész: {video_files[url]}")

        except Exception as e:
            dlog(f"❌ HIBA: {str(e)}")
        finally:
            await context.close()
            await browser.close()
            is_running = False
            dlog("🏁 Scraper leállt.")

# --- FLASK ROUTES ---

@app.route('/')
def console_view():
    """A 'Webes Konzol' felület"""
    url = request.args.get('url')
    
    # Ha van URL és nem fut épp semmi, indítsuk el a háttérben
    if url and not is_running:
        thread = threading.Thread(target=lambda: asyncio.run(run_scraper_logic(url)))
        thread.start()

    return render_template_string(HTML_CONSOLE, 
                                  logs=logs[::-1], # Legfrissebb felül
                                  is_running=is_running,
                                  current_url=url,
                                  hits=last_hits.get(url, []) if url else [],
                                  video=video_files.get(url) if url else None)

@app.route('/videos/<path:filename>')
def serve_video(filename):
    return send_from_directory(VIDEO_DIR, filename)

@app.route('/scrape')
def api_scrape():
    """Hagyományos JSON API"""
    url = request.args.get('url')
    if not url: return jsonify({"error": "No URL"}), 400
    asyncio.run(run_scraper_logic(url))
    return jsonify({"status": "done", "hits": last_hits.get(url, []), "video": video_files.get(url)})

# --- HTML TEMPLATE (Konzol stílus) ---
HTML_CONSOLE = """
<!DOCTYPE html>
<html>
<head>
    <title>Joyn Docker Console</title>
    <meta http-equiv="refresh" content="3">
    <style>
        body { background: #0c0c0c; color: #00ff41; font-family: 'Courier New', monospace; margin: 0; padding: 20px; }
        .header { border-bottom: 2px solid #00ff41; padding-bottom: 10px; margin-bottom: 20px; }
        .status { color: #fff; background: #333; padding: 5px 10px; border-radius: 4px; }
        .running { background: #aa0000; animation: blink 1s infinite; }
        .log-container { background: #1a1a1a; padding: 15px; border-radius: 5px; height: 400px; overflow-y: auto; border: 1px solid #333; }
        .log-entry { margin-bottom: 5px; border-bottom: 1px solid #222; font-size: 14px; }
        .hit-box { margin-top: 20px; color: cyan; }
        video { width: 100%; max-width: 500px; border: 1px solid #00ff41; margin-top: 10px; }
        @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.5;} 100% {opacity: 1;} }
    </style>
</head>
<body>
    <div class="header">
        <h1>🛰️ JOYN-SCANNER CORE V2</h1>
        <p>Status: <span class="status {{ 'running' if is_running else '' }}">
            {{ 'SCANNIG...' if is_running else 'IDLE / READY' }}
        </span></p>
    </div>

    {% if current_url %}
        <div class="hit-box">
            <h3>🎯 Target: {{ current_url }}</h3>
            {% if video %}
                <video controls autoplay muted><source src="/videos/{{ video }}" type="video/webm"></video>
            {% endif %}
            <h4>Found Links ({{ hits|length }}):</h4>
            <ul>{% for h in hits[:5] %}<li>{{ h[:80] }}...</li>{% endfor %}</ul>
        </div>
    {% else %}
        <p>Használat: <code>?url=https://joyn.de/...</code></p>
    {% endif %}

    <h3>💻 Live Console Output:</h3>
    <div class="log-container">
        {% for log in logs %}
            <div class="log-entry">{{ log }}</div>
        {% endfor %}
    </div>
</body>
</html>
"""

if __name__ == '__main__':
    dlog("🔥 Flask szerver indul a 10000-es porton...")
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
