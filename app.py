import asyncio
import nest_asyncio
import os
import sys
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify, send_from_directory
from playwright.async_api import async_playwright

nest_asyncio.apply()
app = Flask(__name__)

# Videók tárolási helye
VIDEO_DIR = "/app/videos"
if not os.path.exists(VIDEO_DIR):
    os.makedirs(VIDEO_DIR)

last_hits = {}
# Itt tároljuk a videó fájlneveket az URL-ekhez
video_files = {}

def dlog(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [JOYN-SCANNER] {msg}")
    sys.stdout.flush()

# Végpont a videók letöltéséhez/megtekintéséhez
@app.route('/videos/<path:filename>')
def serve_video(filename):
    return send_from_directory(VIDEO_DIR, filename)

async def run_sniffer(target_url, cookies=None, max_timeout=90):
    hits = []
    video_path = None
    
    if target_url not in last_hits:
        last_hits[target_url] = []

    async with async_playwright() as p:
        dlog("🚀 Böngésző indítása HEADLESS módban videórögzítéssel...")
        
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        
        # VIDEÓ BEÁLLÍTÁSA: Itt adjuk meg hova mentse
        context = await browser.new_context(
            locale="de-DE",
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
            record_video_dir=VIDEO_DIR,
            record_video_size={'width': 1280, 'height': 720}
        )

        page = await context.new_page()
        
        # Videó fájlnév kinyerése
        video_obj = await page.video.path()
        video_filename = os.path.basename(video_obj) if video_obj else "rögzítés..."
        video_files[target_url] = video_filename

        # Sniffer logika marad...
        def handle_request(req):
            if any(x in req.url.lower() for x in ["m3u8", "playlist", "manifest"]):
                if req.url not in hits:
                    hits.append(req.url)
                    last_hits[target_url].append(req.url)

        page.on("request", handle_request)

        try:
            dlog(f"📡 Navigálás: {target_url}")
            await page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            # Gombnyomkodás imitálása (Cookie + Play)
            # ... (a korábbi kódod gombnyomkodó része ide jön) ...
            await asyncio.sleep(15) # Hagyunk időt a videónak is, hogy rögzítsen valamit

        except Exception as e:
            dlog(f"❌ HIBA: {e}")
        finally:
            # A videó CSAK a context/browser bezárásakor mentődik el véglegesen!
            await context.close() 
            await browser.close()
            # Átnevezzük a videót valami olvashatóbbra, ha kész
            final_path = await page.video.path()
            dlog(f"📹 Videó mentve: {final_path}")
            video_files[target_url] = os.path.basename(final_path)
    
    return hits

# --- HTML SABLON FRISSÍTÉSE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Joyn Monitor + Video</title>
    <meta http-equiv="refresh" content="10">
    <style>
        body { background: #1a1a1a; color: #eee; font-family: sans-serif; padding: 20px; }
        .box { border: 1px solid #444; padding: 20px; background: #222; border-radius: 8px; }
        .hit { background: #000; border-left: 5px solid #00ff41; padding: 10px; margin: 5px 0; font-size: 12px; word-break: break-all; }
        video { width: 100%; max-width: 600px; border: 1px solid #555; margin-top: 10px; }
        .video-link { color: #00ff41; text-decoration: none; font-weight: bold; }
    </style>
</head>
<body>
    <div class="box">
        <h2>🛰️ JOYN SNIFFER (Headless + Video)</h2>
        <p>Target: {{ url }}</p>
        <hr>
        {% if video %}
            <p>📹 Utolsó rögzített folyamat:</p>
            <video controls>
                <source src="/videos/{{ video }}" type="video/webm">
                A böngésződ nem támogatja a videót.
            </video>
            <br>
            <a class="video-link" href="/videos/{{ video }}" target="_blank">📥 Videó letöltése</a>
        {% else %}
            <p>⏳ Videó generálása folyamatban...</p>
        {% endif %}
        <hr>
        <h3>🎯 Talált linkek:</h3>
        {% for link in links %}
            <div class="hit">{{ link }}</div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/web')
def web_view():
    url = request.args.get('url')
    if not url: return "Adj meg egy URL-t!", 400
    
    if url not in last_hits:
        last_hits[url] = []
        asyncio.get_event_loop().create_task(run_sniffer(url))
    
    return render_template_string(HTML_TEMPLATE, 
                                 url=url, 
                                 links=last_hits.get(url, []), 
                                 video=video_files.get(url))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
