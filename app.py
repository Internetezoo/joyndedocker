import asyncio
import os
import sys
import threading
from datetime import datetime
from flask import Flask, request, send_from_directory, render_template_string
from playwright.async_api import async_playwright

app = Flask(__name__)

# Mappák létrehozása
VIDEO_DIR = os.path.join(os.getcwd(), "videos")
os.makedirs(VIDEO_DIR, exist_ok=True)

# Globális állapot
state = {
    "logs": [],
    "is_running": False,
    "current_url": "",
    "video_file": None,
    "links": []
}

def dlog(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    print(entry)
    sys.stdout.flush()
    state["logs"].append(entry)
    if len(state["logs"]) > 50: state["logs"].pop(0)

async def scraper_task(url):
    state["is_running"] = True
    state["current_url"] = url
    state["links"] = []
    state["video_file"] = None
    state["logs"] = []
    
    async with async_playwright() as p:
        dlog(f"🚀 Sniper indítása (60s rögzítés): {url}")
        try:
            browser = await p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-setuid-sandbox']
            )
            
            context = await browser.new_context(
                record_video_dir=VIDEO_DIR,
                viewport={'width': 1280, 'height': 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()

            # M3U8 Sniffer
            page.on("request", lambda req: (
                state["links"].append(req.url),
                dlog(f"🎯 M3U8 TALÁLAT: {req.url[:50]}...")
            ) if "m3u8" in req.url.lower() and req.url not in state["links"] else None)

            dlog("🌐 Oldal betöltése...")
            await page.goto(url, wait_until="commit", timeout=60000)

            cookie_pressed = False
            start_time = datetime.now()

            # CIKLUS: Süti keresése, majd 60mp várakozás
            while True:
                elapsed = (datetime.now() - start_time).seconds
                if elapsed > 180: # Max 3 percig futhat az egész folyamat
                    dlog("⏱️ Maximális időtúllépés (180s).")
                    break

                if not cookie_pressed:
                    try:
                        selectors = [
                            "button:has-text('Alle akzeptieren')", 
                            "cmp-button button.button--primary", 
                            "button.button--primary",
                            "#cmp-welcome-confirm-all"
                        ]
                        for sel in selectors:
                            btn = page.locator(sel).first
                            if await btn.is_visible(timeout=500):
                                await btn.click(force=True)
                                dlog("✅ SÜTI GOMB MEGNYOMVA! Most indul a 60 másodperces rögzítés...")
                                cookie_pressed = True
                                break
                    except: pass
                
                # Ha megnyomtuk a sütit, várunk 60 másodpercet és kész
                if cookie_pressed:
                    # Percenkénti visszaszámlálás a logban
                    for i in range(6):
                        await asyncio.sleep(10)
                        dlog(f"📹 Rögzítés folyamatban... ({10*(i+1)}/60s)")
                    
                    dlog("🏁 60 másodperc letelt. Lezárom a böngészőt.")
                    break

                await asyncio.sleep(2)
                if elapsed % 10 == 0:
                    dlog(f"📡 Keresés... ({elapsed}s)")

            # Fontos a context lezárása a videó mentéséhez
            await context.close()
            video_path = await page.video.path()
            state["video_file"] = os.path.basename(video_path)
            
            video_url = f"{request.host_url}videos/{state['video_file']}"
            dlog(f"✨ KÉSZ! Letölthető videó: {video_url}")

        except Exception as e:
            dlog(f"❌ HIBA: {str(e)}")
        finally:
            await browser.close()
            state["is_running"] = False

# --- HTML DASHBOARD ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Joyn Sniper V5 - 60s Record</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { margin: 0; font-family: sans-serif; background: #0a0a0a; color: #fff; display: flex; flex-direction: column; height: 100vh; }
        .top-bar { background: #111; padding: 15px; display: flex; gap: 10px; border-bottom: 2px solid #00ff41; align-items: center; }
        input { flex: 1; padding: 10px; background: #000; color: #00ff41; border: 1px solid #333; border-radius: 4px; }
        button { padding: 10px 20px; background: #00ff41; color: #000; border: none; font-weight: bold; border-radius: 4px; cursor: pointer; }
        button:disabled { background: #333; color: #666; }
        .main { display: flex; flex: 1; overflow: hidden; }
        .view { flex: 1.5; padding: 20px; overflow-y: auto; border-right: 1px solid #222; }
        .logs { flex: 1; padding: 20px; background: #050505; color: #00ff41; font-family: monospace; overflow-y: auto; }
        video { width: 100%; border: 1px solid #222; border-radius: 8px; }
        .m3u8 { background: #111; padding: 5px; border-left: 3px solid cyan; margin-bottom: 5px; font-size: 11px; word-break: break-all; }
        .pulse { width: 10px; height: 10px; background: red; border-radius: 50%; display: inline-block; animation: blink 1s infinite; }
        @keyframes blink { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }
    </style>
</head>
<body>
    <div class="top-bar">
        <form action="/" method="GET" style="display:contents;">
            <input type="text" name="url" placeholder="Joyn link..." value="{{ state.current_url }}">
            <button type="submit" {{ 'disabled' if state.is_running else '' }}>SCAN INDÍTÁSA</button>
        </form>
        {% if state.is_running %}<span class="pulse"></span> REC{% endif %}
    </div>
    <div class="main">
        <div class="view">
            <h3>🎬 Videó kimenet (60mp rögzítés)</h3>
            {% if state.video_file %}
                <video controls autoplay><source src="/videos/{{ state.video_file }}" type="video/webm"></video>
                <p><a href="/videos/{{ state.video_file }}" style="color:#00ff41;" download>📥 VIDEÓ MENTÉSE</a></p>
            {% elif state.is_running %}
                <div style="height:300px; border:1px dashed #444; display:flex; align-items:center; justify-content:center; color:#888;">
                    📡 A robot éppen dolgozik... Süti után 60 másodpercig rögzít.
                </div>
            {% else %}
                <p style="color:#444;">Nincs rögzítés.</p>
            {% endif %}
            <h3>🎯 Talált linkek</h3>
            {% for l in state.links %}<div class="m3u8">{{ l }}</div>{% endfor %}
        </div>
        <div class="logs">
            <h3>💻 Log</h3>
            {% for log in state.logs[::-1] %}<div>{{ log }}</div>{% endfor %}
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    url = request.args.get('url')
    if url and not state["is_running"]:
        threading.Thread(target=lambda: asyncio.run(scraper_task(url))).start()
    return render_template_string(HTML_TEMPLATE, state=state)

@app.route('/videos/<path:filename>')
def serve_video(filename):
    return send_from_directory(VIDEO_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)), threaded=True)
