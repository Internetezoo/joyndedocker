import asyncio
import os
import sys
import threading
from datetime import datetime
from flask import Flask, request, send_from_directory, render_template_string
from playwright.async_api import async_playwright

app = Flask(__name__)

# Mappák létrehozása a videóknak
VIDEO_DIR = os.path.join(os.getcwd(), "videos")
os.makedirs(VIDEO_DIR, exist_ok=True)

# Globális állapot a webes konzolnak
state = {
    "logs": [],
    "is_running": False,
    "current_url": "",
    "video_file": None,
    "links": []
}

def dlog(msg):
    """Naplózás a konzolba és a webes felületre"""
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
    state["logs"] = [] # Frissítésnél ürítjük a naplót
    
    async with async_playwright() as p:
        dlog(f"🚀 Sniper indítása: {url}")
        try:
            # Böngésző indítása Docker-optimalizált paraméterekkel
            browser = await p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-setuid-sandbox']
            )
            
            # Környezet létrehozása videórögzítéssel
            context = await browser.new_context(
                record_video_dir=VIDEO_DIR,
                viewport={'width': 1280, 'height': 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()

            # M3U8 figyelő (ha közben elkap valamit, kiírja)
            page.on("request", lambda req: (
                state["links"].append(req.url),
                dlog(f"🎯 M3U8 DETEKTÁLVA: {req.url[:50]}...")
            ) if "m3u8" in req.url.lower() and req.url not in state["links"] else None)

            dlog("🌐 Oldal betöltése (Navigation)...")
            await page.goto(url, wait_until="commit", timeout=60000)

            cookie_pressed = False
            start_time = datetime.now()

            # AGRESSZÍV CIKLUS: Keressük a sütit, majd várunk 10 mp-et
            while True:
                elapsed = (datetime.now() - start_time).seconds
                if elapsed > 120:
                    dlog("⏱️ Időtúllépés (120s). Leállítom a folyamatot.")
                    break

                if not cookie_pressed:
                    # Shadow DOM kompatibilis süti-keresés
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
                                dlog("✅ SÜTI GOMB MEGNYOMVA! Elindítom a 10 másodperces rögzítést...")
                                cookie_pressed = True
                                break
                    except: pass
                
                # Ha megvolt a gombnyomás, várunk 10 másodpercet és vége a dalnak
                if cookie_pressed:
                    await asyncio.sleep(10)
                    dlog("🏁 10 másodperc letelt. Lezárom a böngészőt és mentem a videót.")
                    break

                await asyncio.sleep(2)
                if elapsed % 10 == 0:
                    dlog(f"📡 Keresés folyamatban... ({elapsed}s)")

            # Nagyon fontos: a context-et be kell zárni a videó véglegesítéséhez!
            await context.close()
            video_path = await page.video.path()
            state["video_file"] = os.path.basename(video_path)
            
            # Teljes elérési út generálása a logba
            video_url = f"{request.host_url}videos/{state['video_file']}"
            dlog(f"✨ KÉSZ! Videó link: {video_url}")

        except Exception as e:
            dlog(f"❌ HIBA: {str(e)}")
        finally:
            await browser.close()
            state["is_running"] = False

# --- HTML INTERFACE (Két részre osztott nézet) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Joyn Sniper V4 - Cookie Fix</title>
    <meta http-equiv="refresh" content="4">
    <style>
        body { margin: 0; font-family: 'Segoe UI', sans-serif; background: #0c0c0c; color: #fff; display: flex; flex-direction: column; height: 100vh; }
        .top-bar { background: #1a1a1a; padding: 15px; display: flex; gap: 10px; align-items: center; border-bottom: 2px solid #00ff41; }
        input { flex: 1; padding: 12px; border-radius: 5px; border: 1px solid #333; background: #000; color: #00ff41; outline: none; }
        button { padding: 12px 20px; background: #00ff41; color: #000; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
        button:disabled { background: #444; color: #888; }
        
        .main { display: flex; flex: 1; overflow: hidden; }
        .left { flex: 1.5; padding: 20px; border-right: 1px solid #222; overflow-y: auto; }
        .right { flex: 1; background: #050505; padding: 20px; overflow-y: auto; font-family: 'Consolas', monospace; color: #00ff41; }
        
        video { width: 100%; border: 1px solid #00ff41; border-radius: 8px; margin-bottom: 20px; background: #000; }
        .link-item { background: #111; padding: 8px; border-left: 3px solid #00ff41; margin-bottom: 5px; font-size: 11px; word-break: break-all; color: #00e5ff; }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .active { background: #ff4444; animation: pulse 1s infinite; }
        @keyframes pulse { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }
    </style>
</head>
<body>

    <div class="top-bar">
        <form action="/" method="GET" style="display:contents;">
            <input type="text" name="url" placeholder="Joyn link..." value="{{ state.current_url }}">
            <button type="submit" {{ 'disabled' if state.is_running else '' }}>SCAN INDÍTÁSA</button>
        </form>
        <div style="font-size: 12px; margin-left: 20px;">
            <span class="status-dot {{ 'active' if state.is_running else '' }}" style="background: {{ '#ff4444' if state.is_running else '#444' }};"></span>
            {{ 'SZENZOR AKTÍV' if state.is_running else 'KÉSZ' }}
        </div>
    </div>

    <div class="main">
        <div class="left">
            <h3>📹 Eredmény Videó (Shadow DOM rögzítés)</h3>
            {% if state.video_file %}
                <video controls autoplay>
                    <source src="/videos/{{ state.video_file }}" type="video/webm">
                </video>
                <p><a href="/videos/{{ state.video_file }}" style="color:#00ff41;" download>📥 VIDEÓ LETÖLTÉSE</a></p>
            {% elif state.is_running %}
                <div style="height:300px; border:1px dashed #444; display:flex; align-items:center; justify-content:center; color:#888; text-align:center;">
                    📡 Robot dolgozik...<br>Várom a süti gombot, utána +10mp rögzítés!
                </div>
            {% else %}
                <p style="color:#555;">Nincs aktív rögzítés.</p>
            {% endif %}

            <h3>🎯 Detektált M3U8 linkek</h3>
            {% for link in state.links %}
                <div class="link-item">{{ link }}</div>
            {% endfor %}
        </div>

        <div class="right">
            <h3>💻 Live Log</h3>
            {% for log in state.logs[::-1] %}
                <div style="margin-bottom:4px; border-bottom: 1px solid #111;">{{ log }}</div>
            {% endfor %}
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
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)
