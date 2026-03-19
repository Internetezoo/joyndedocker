import asyncio
import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from playwright.async_api import async_playwright

app = Flask(__name__)

# Videók mappája
VIDEO_DIR = os.path.join(os.getcwd(), "videos")
if not os.path.exists(VIDEO_DIR):
    os.makedirs(VIDEO_DIR, exist_ok=True)

# Globális tároló a találatoknak
results_cache = {}

def dlog(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

@app.route('/videos/<path:filename>')
def serve_video(filename):
    return send_from_directory(VIDEO_DIR, filename)

async def start_browser_and_scrape(url):
    """Külön aszinkron logika a böngészőhöz"""
    hits = []
    video_name = None
    
    async with async_playwright() as p:
        dlog(f"🚀 Böngésző indítása: {url}")
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        
        context = await browser.new_context(
            record_video_dir=VIDEO_DIR,
            viewport={'width': 1280, 'height': 720}
        )
        
        page = await context.new_page()
        
        # Figyeljük az m3u8 linkeket
        page.on("request", lambda req: hits.append(req.url) if "m3u8" in req.url.lower() else None)

        try:
            # 60 másodperces timeout a betöltésre
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Várunk kicsit, hogy elinduljon a stream és legyen videó
            await asyncio.sleep(10) 
            
            # Videó fájl kinyerése
            video_path = await page.video.path()
            video_name = os.path.basename(video_path) if video_path else None
            
        except Exception as e:
            dlog(f"❌ Hiba: {str(e)}")
        finally:
            await context.close()
            await browser.close()
            
    return hits, video_name

@app.route('/')
def home():
    return "SZERVER ONLINE. Használat: /scrape?url=..."

@app.route('/scrape')
def scrape():
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({"error": "Hiányzó URL"}), 400

    dlog(f"📥 Beérkező kérés: {target_url}")

    # Itt futtatjuk le az aszinkron kódot szinkron módon a Flask-en belül
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        hits, video = loop.run_until_complete(start_browser_and_scrape(target_url))
        loop.close()

        return jsonify({
            "status": "success",
            "url": target_url,
            "m3u8_links": list(set(hits)), # Duplikációk kiszűrése
            "video_url": f"{request.host_url}videos/{video}" if video else None
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Render port kezelése
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
