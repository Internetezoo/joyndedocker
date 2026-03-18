import asyncio
import nest_asyncio
import os
import json
import sys
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify
from playwright.async_api import async_playwright

# Engedélyezzük az egymásba ágyazott eseményhurkokat
nest_asyncio.apply()

app = Flask(__name__)

# Memória a /web nézethez (URL -> talált linkek listája)
last_hits = {}

def dlog(msg):
    """Részletes logolás a Render konzolba"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [JOYN-SCANNER] {msg}")
    sys.stdout.flush()

async def run_sniffer(target_url, cookies=None, max_timeout=120):
    """
    Addig nyomkodja a gombokat, amíg meg nem érkezik az m3u8 link.
    max_timeout: 120 másodperc után feladja, ha semmi nem jött.
    """
    hits = []
    start_time = asyncio.get_event_loop().time()
    
    # Biztosítjuk, hogy legyen lista az URL-hez a memóriában
    if target_url not in last_hits:
        last_hits[target_url] = []

    async with async_playwright() as p:
        dlog(f"🚀 Böngésző indítása... Cél: {target_url}")
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            locale="de-DE",
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
        )

        # Sütik betöltése és Geo-fix
        if cookies:
            cleaned_cookies = []
            for cookie in cookies:
                c = cookie.copy()
                if c.get('name') == 'geoLocation': c['value'] = 'de'
                c.pop('hostOnly', None)
                c.pop('storeId', None)
                cleaned_cookies.append(c)
            await context.add_cookies(cleaned_cookies)
            dlog(f"🍪 {len(cleaned_cookies)} süti betöltve.")

        page = await context.new_page()

        # Hálózati figyelő: amint jön egy m3u8, beleteszi a listába
        def handle_request(req):
            url_low = req.url.lower()
            if any(x in url_low for x in ["m3u8", "playlist", "manifest", "master"]):
                if req.url not in hits:
                    hits.append(req.url)
                    dlog(f"🎯 TALÁLAT! Elkapva: {req.url[:70]}...")
                    if req.url not in last_hits[target_url]:
                        last_hits[target_url].append(req.url)

        page.on("request", handle_request)

        try:
            dlog("📡 Navigálás az oldalra...")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            
            # --- AGRESSZÍV GOMBNYOMKODÓ CIKLUS ---
            dlog("🔄 Kezdem a 'brute-force' gombnyomkodást...")
            
            while len(hits) == 0:
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                
                if elapsed > max_timeout:
                    dlog(f"⏱️ IDŐTÚLLÉPÉS ({max_timeout}s). Nem sikerült m3u8-at fogni.")
                    break

                # 1. Cookie gombok (németül)
                cookie_selectors = [
                    "button:has-text('Alle akzeptieren')",
                    "button:has-text('Zustimmen')",
                    "button:has-text('Akzeptieren')",
                    "#cmp-welcome-confirm-all",
                    "button[id*='accept']"
                ]
                for sel in cookie_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=300):
                            await btn.click(force=True)
                            dlog(f"[{elapsed}s] 🖱️ Cookie gomb megnyomva!")
                    except: pass

                # 2. Play gomb (ha látható)
                try:
                    play_btn = page.locator("[data-testid='play-button'], button:has-text('Abspielen')").first
                    if await play_btn.is_visible(timeout=300):
                        await play_btn.click(force=True)
                        dlog(f"[{elapsed}s] ▶️ Play gomb megnyomva!")
                except: pass

                # Rövid várakozás a következő kör előtt (hogy a JS tudjon futni)
                await asyncio.sleep(1.5)

            if len(hits) > 0:
                dlog(f"✨ SIKER! Összesen {len(hits)} linket találtam.")

        except Exception as e:
            dlog(f"❌ HIBA: {str(e)}")
        finally:
            dlog("🧹 Böngésző leállítása.")
            await browser.close()
    
    return hits

# --- FLASK ÚTVONALAK ---

@app.route('/web')
def web_view():
    url = request.args.get('url')
    if not url: return "Adj meg egy URL-t: /web?url=...", 400

    # Ha még nem kerestünk rá, indítunk egy taskot
    if url not in last_hits or not last_hits[url]:
        last_hits[url] = []
        dlog(f"WEB-KÉRÉS: {url}")
        asyncio.get_event_loop().create_task(run_sniffer(url))
    
    return render_template_string(HTML_TEMPLATE, url=url, links=last_hits[url])

@app.route('/scrape', methods=['GET', 'POST'])
def scrape_api():
    user_cookies = []
    if request.method == 'POST':
        data = request.get_json()
        url = data.get('url')
        user_cookies = data.get('cookies', [])
    else:
        url = request.args.get('url')

    if not url: return jsonify({"status": "error", "message": "Nincs URL"}), 400
    
    dlog(f"API-KÉRÉS: {url}")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(run_sniffer(url, cookies=user_cookies))
        return jsonify({"status": "success", "hits": results})
    finally:
        loop.close()

@app.route('/')
def index():
    return "JOYN SNIFFER ONLINE. Használd a /web?url=... vagy /scrape útvonalat."

# --- HTML DESIGN ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Joyn Live Monitor</title>
    <meta http-equiv="refresh" content="3">
    <style>
        body { background: #050505; color: #00ff41; font-family: 'Courier New', monospace; padding: 20px; }
        .box { border: 1px solid #00ff41; padding: 20px; background: #0a0a0a; border-radius: 5px; }
        .hit { background: #111; border: 1px solid #333; padding: 10px; margin: 10px 0; word-break: break-all; font-size: 12px; border-left: 5px solid #00ff41; }
        .loading { color: orange; animation: blink 1s infinite; font-weight: bold; }
        @keyframes blink { 0% {opacity:1} 50% {opacity:0.4} 100% {opacity:1} }
        h1 { color: #fff; text-shadow: 0 0 10px #00ff41; }
    </style>
</head>
<body>
    <div class="box">
        <h1>🛰️ JOYN TRAFFIC SNIFFER</h1>
        <p style="color: #888;">Cél URL: {{ url }}</p>
        <hr style="border: 0.5px solid #222;">
        
        {% if links %}
            <p style="color: #fff;">✅ TALÁLT LINKEK ({{ links|length }} db):</p>
            {% for link in links %}
                <div class="hit"><b>[STREAM]:</b> {{ link }}</div>
            {% endfor %}
            <p style="font-size: 0.8em; color: #555;">(Ha újabb linket akarsz, frissítsd az oldalt paraméter nélkül, majd újra URL-lel.)</p>
        {% else %}
            <p class="loading">📡 KERESÉS FOLYAMATBAN...</p>
            <p>A szerver éppen próbálja megnyomni a gombokat és elkapni az m3u8 linket. Várj türelemmel, ez 20-60 másodperc is lehet.</p>
        {% endif %}
    </div>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    dlog(f"Szerver indul a {port} porton...")
    app.run(host='0.0.0.0', port=port)
