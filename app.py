import asyncio
import nest_asyncio
import os
import sys
import json
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify
from playwright.async_api import async_playwright

# Engedélyezzük az egymásba ágyazott eseményhurkokat
nest_asyncio.apply()

app = Flask(__name__)

# Memória a talált linkeknek
last_hits = {}

def dlog(msg):
    """Debug log a Render konzolba"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [JOYN-SCANNER] {msg}")
    sys.stdout.flush()

async def run_sniffer(target_url, cookies=None, max_timeout=120):
    hits = []
    start_time = asyncio.get_event_loop().time()
    
    if target_url not in last_hits:
        last_hits[target_url] = []

    async with async_playwright() as p:
        dlog("🎭 Böngésző indítása (Xvfb / Non-Headless emuláció)...")
        
        # Headless=False kell, hogy ne detektálják botnak, 
        # de a Renderen ehhez xvfb-run kell!
        browser = await p.chromium.launch(
            headless=False, 
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--use-gl=swiftshader', # GPU nélküli renderelés
                '--window-size=1280,720'
            ]
        )
        
        context = await browser.new_context(
            locale="de-DE",
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
        )

        # Webdriver flag törlése (Bot-védelem kijátszása)
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        if cookies:
            cleaned_cookies = []
            for cookie in cookies:
                c = cookie.copy()
                if c.get('name') == 'geoLocation': c['value'] = 'de'
                c.pop('hostOnly', None); c.pop('storeId', None)
                cleaned_cookies.append(c)
            await context.add_cookies(cleaned_cookies)
            dlog(f"🍪 {len(cleaned_cookies)} süti betöltve.")

        # Hálózati figyelő
        def handle_request(req):
            url_low = req.url.lower()
            if any(x in url_low for x in ["m3u8", "playlist", "manifest"]):
                if req.url not in hits:
                    hits.append(req.url)
                    dlog(f"🎯 TALÁLAT: {req.url[:60]}...")
                    if req.url not in last_hits[target_url]:
                        last_hits[target_url].append(req.url)

        page.on("request", handle_request)

        try:
            dlog(f"📡 Navigálás: {target_url}")
            # A 'networkidle' megvárja, amíg elcsendesedik a hálózat (jobb a Joyn-nál)
            await page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            dlog("🔄 Kezdem az agresszív gombnyomkodást...")
            
            while len(hits) == 0:
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                if elapsed > max_timeout:
                    dlog("⏱️ Időtúllépés. Nem jött m3u8.")
                    break

                # --- COOKIE KEZELÉS ---
                for sel in ["button:has-text('Alle akzeptieren')", "button:has-text('Zustimmen')", "#cmp-welcome-confirm-all"]:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=500):
                            await btn.click(force=True)
                            dlog(f"[{elapsed}s] 🖱️ Cookie OK")
                    except: pass

                # --- PLAY GOMB ---
                try:
                    play_btn = page.locator("[data-testid='play-button'], button:has-text('Abspielen')").first
                    if await play_btn.is_visible(timeout=500):
                        await play_btn.click(force=True)
                        dlog(f"[{elapsed}s] ▶️ Play OK")
                except: pass

                await asyncio.sleep(2)

        except Exception as e:
            dlog(f"❌ HIBA: {str(e)}")
        finally:
            dlog("🧹 Bezárás.")
            await browser.close()
    
    return hits

# --- FLASK ÚTVONALAK ---

@app.route('/web')
def web_view():
    url = request.args.get('url')
    if not url: return "Adj meg egy URL-t: /web?url=...", 400
    if url not in last_hits or not last_hits[url]:
        last_hits[url] = []
        asyncio.get_event_loop().create_task(run_sniffer(url))
    return render_template_string(HTML_TEMPLATE, url=url, links=last_hits[url])

@app.route('/scrape', methods=['POST'])
def scrape_api():
    data = request.get_json()
    url = data.get('url')
    cookies = data.get('cookies', [])
    if not url: return jsonify({"status": "error"}), 400
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(run_sniffer(url, cookies=cookies))
        return jsonify({"status": "success", "hits": results})
    finally:
        loop.close()

@app.route('/')
def index(): return "JOYN SNIFFER ACTIVE"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Joyn Monitor</title>
    <meta http-equiv="refresh" content="4">
    <style>
        body { background: #000; color: #0f0; font-family: monospace; padding: 20px; }
        .hit { background: #111; border: 1px solid #0f0; padding: 10px; margin: 10px 0; word-break: break-all; }
        .loading { color: orange; animation: blink 1s infinite; }
        @keyframes blink { 0% {opacity:1} 50% {opacity:0.4} 100% {opacity:1} }
    </style>
</head>
<body>
    <h2>🛰️ JOYN TRAFFIC SNIFFER (XVFB MODE)</h2>
    <p>Target: {{ url }}</p>
    <hr>
    {% if links %}
        {% for link in links %}
            <div class="hit"><b>[FOUND]:</b> {{ link }}</div>
        {% endfor %}
    {% else %}
        <p class="loading">📡 KERESÉS ÉS GOMBNYOMKODÁS FOLYAMATBAN...</p>
    {% endif %}
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
