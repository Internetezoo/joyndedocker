import asyncio
import os
import sys
import threading
from datetime import datetime
from flask import Flask, request, send_from_directory, render_template_string
from playwright.async_api import async_playwright

app = Flask(__name__)

# Mappák előkészítése
VIDEO_DIR = os.path.join(os.getcwd(), "videos")
os.makedirs(VIDEO_DIR, exist_ok=True)

# Globális állapot a webes felületnek
state = {
    "logs": [],
    "is_running": False,
    "current_url": "",
    "video_file": None,
    "links": []
}

def dlog(msg):
    """Részletes naplózás a konzolba és a webes felületre"""
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
    state["logs"] = [] # Új indításkor tiszta lap
    
    async with async_playwright() as p:
        dlog(f"🚀 Sniper indítása: {url}")
        try:
            # Böngésző indítása stabilizáló kapcsolókkal
            browser = await p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-setuid-sandbox']
            )
            
            # Videórögzítés beállítása
            context = await browser.new_context(
                record_video_dir=VIDEO_DIR,
                viewport={'width': 1280, 'height': 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()

            # Hálózati forgalom figyelése (M3U8 Sniffer)
            page.on("request", lambda req: (
                state["links"].append(req.url),
                dlog(f"🎯 TALÁLAT: {req.url[:60]}...")
            ) if "m3u8" in req.url.lower() and req.url not in state["links"] else None)

            # Navigáció (csak a kezdeti betöltésig várunk, utána a ciklus dolgozik)
            dlog("🌐 Oldal betöltése...")
            await page.goto(url, wait_until="commit", timeout=60000)

            start_time = datetime.now()
            # AGRESSZÍV CIKLUS: Addig nyomkodunk, amíg meg nincs a link vagy lejár az idő
            while len(state["links"]) == 0:
                elapsed = (datetime.now() - start_time).seconds
                if elapsed > 100:
                    dlog("⏱️ Időtúllépés (100s). Leállítom a keresést.")
                    break

                # 1. SÜTI / CMP GOMB (Shadow DOM áttöréssel)
                # A Playwright '>>' vagy sima CSS szelektorai átlátnak a shadow root-okon
                try:
                    cookie_selectors = [
                        "button:has-text('Alle akzeptieren')", 
                        "cmp-button button.button--primary", 
                        "button.button--primary",
                        "#cmp-welcome-confirm-all"
                    ]
                    for sel in cookie_selectors:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=500):
                            await btn.click(force=True)
                            dlog(f"🖱️ Süti gomb megnyomva: {sel}")
                except: pass

                # 2. PLAY GOMB KERESÉSE
                try:
                    play_selectors = [
                        "[data-testid='play-button']", 
                        "button:has-text('Abspielen')", 
                        ".play-icon",
                        "video" # Néha a videóra kattintás indítja el
                    ]
                    for sel in play_selectors:
                        play_btn = page.locator(sel).first
                        if await play_btn.is_visible(timeout=500):
                            await play_btn.click(force=True)
                            dlog(f"▶️ Play gomb megnyomva: {sel}")
                except: pass

                # Kis szünet a próbálkozások között
                await asyncio.sleep(2)
                if elapsed % 10 == 0:
                    dlog(f"📡 Keresés folyamatban... ({elapsed}s)")

            # Ha megvan a link, várunk még kicsit a videó miatt
            if state["links"]:
                dlog("✨ SIKER! Playlist linkek rögzítve.")
                await asyncio.sleep(8)

            # Videófájl mentése
            video_path = await page.video.path()
            state["video_file"] = os.path.basename(video_path)
            dlog(f"🏁 Folyamat lezárva. Videó: {state['video_file']}")

        except Exception as e:
            dlog(f"❌ HIBA: {str(e)}")
        finally:
            await context.close()
            await browser.close()
            state["is_running"] = False

# --- HTML DASHBOARD (Két részes felület) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Joyn Sniper Dashboard</title>
    <meta http-equiv="refresh" content="4">
    <style>
        body { margin: 0; font-family: 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
        .top-bar { background: #1a1a1a; padding: 15px 25px; display: flex; gap: 15px; align-items: center; border-bottom: 2px solid #00ff41; }
        input { flex: 1; padding: 12px; border-radius: 6px; border: 1px solid #333; background: #000; color: #00ff41; font-size: 15px; outline: none; }
        button { padding: 12px 25px; background: #00ff41; color: #000; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }
        button:disabled { background: #333; color: #777; cursor: not-allowed; }
        
        .main { display: flex; flex: 1; overflow: hidden; }
        .left-panel { flex: 1.4; padding: 20px; overflow-y: auto; border-right: 1px solid #222; }
        .right-panel { flex: 1; background: #050505; padding: 20px; overflow-y: auto; font-family: 'Consolas', monospace; color: #00ff41; }
        
        video { width: 100%; border-radius: 8px; border: 1px solid #333; background: #000; margin-bottom: 20px; }
        .hit-item { background: #111; padding: 10px; border-left: 4px solid #00ff41; margin-bottom: 8px; font-size: 12px; word-break: break-all; color: #00e5ff; }
        .status-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px; }
        .status-active { background: #ff4444; animation: pulse 1s infinite; }
        .status-idle { background: #444; }
        
        h3 { margin-top: 0; color: #00ff41; font-size: 18px; text-transform: uppercase; letter-spacing: 1px; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    </style>
</head>
<body>

    <div class="top-bar">
        <form action="/" method="GET" style="display:contents;">
            <input type="text" name="url" placeholder="Joyn videó URL (pl. https://www.joyn.de/play/...)" value="{{ state.current_url }}">
            <button type="submit" {{ 'disabled' if state.is_running else '' }}>
                {{ 'FOLYAMATBAN...' if state.is_running else 'SCAN INDÍTÁSA' }}
            </button>
        </form>
        <div style="font-size: 13px;">
            <span class="status-dot {{ 'status-active' if state.is_running else 'status-idle' }}"></span>
            {{ 'SZENZOR AKTÍV' if state.is_running else 'KÉSZENLÉT' }}
        </div>
    </div>

    <div class="main">
        <div class="left-panel">
            <h3>🎬 Élő rögzített kép</h3>
            {% if state.video_file %}
                <video controls autoplay muted>
                    <source src="/videos/{{ state.video_file }}" type="video/webm">
                </video>
                <p><a href="/videos/{{ state.video_file }}" style="color:#00ff41; text-decoration:none;" download>📥 Videó letöltése / Mentés</a></p>
            {% elif state.is_running %}
                <div style="height:300px; border:1px dashed #333; display:flex; align-items:center; justify-content:center; color:#666;">
                    📡 A robot dolgozik... A videó a folyamat végén generálódik.
                </div>
            {% else %}
                <p style="color:#555;">Nincs aktív rögzítés. Adj meg egy URL-t felül.</p>
            {% endif %}

            <h3>🎯 Talált M3U8 Playlistek</h3>
            {% for link in state.links %}
                <div class="hit-item">{{ link }}</div>
            {% else %}
                <p style="color:#444;">Még nincsenek találatok.</p>
            {% endfor %}
        </div>

        <div class="right-panel">
            <h3>💻 Rendszernapló (Logs)</h3>
            {% for log in state.logs[::-1] %}
                <div style="margin-bottom:5px; border-bottom: 1px solid #111; padding-bottom:3px;">
                    <span style="color:#888;">{{ log[:10] }}</span> {{ log[10:] }}
                </div>
            {% endfor %}
        </div>
    </div>

</body>
</html>
"""

@app.route('/')
def index():
    target_url = request.args.get('url')
    if target_url and not state["is_running"]:
        # Háttérszálon indítjuk a scrapelést, hogy a Flask válaszolni tudjon
        threading.Thread(target=lambda: asyncio.run(scraper_task(target_url))).start()
    return render_template_string(HTML_TEMPLATE, state=state)

@app.route('/videos/<path:filename>')
def serve_video(filename):
    """Végpont a videók kiszolgálásához"""
    return send_from_directory(VIDEO_DIR, filename)

if __name__ == '__main__':
    # Render port és host beállítása
    port = int(os.environ.get("PORT", 10000))
    dlog(f"🔥 Joyn Sniper Dashboard indul a {port}-os porton...")
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False)
