import asyncio
import nest_asyncio
import os
import sys
import json
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify
from playwright.async_api import async_playwright

# Engedélyezzük az egymásba ágyazott eseményhurkokat a Flask/Render környezetben
nest_asyncio.apply()

app = Flask(__name__)

# Memória a talált linkek tárolására (URL -> lista)
last_hits = {}

def dlog(msg):
    """Részletes logolás a Render konzolba időbélyeggel"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [JOYN-SCANNER] {msg}")
    sys.stdout.flush()

async def run_sniffer(target_url, cookies=None, max_timeout=120):
    """
    Fő motor: Elindítja a böngészőt non-headless módban, 
    és addig próbálkozik, amíg m3u8 linket nem talál.
    """
    hits = []
    start_time = asyncio.get_event_loop().time()
    
    if target_url not in last_hits:
        last_hits[target_url] = []

    async with async_playwright() as p:
        dlog("🎭 Böngésző indítása (Xvfb / Non-Headless emuláció)...")
        
        # A headless=False kritikus a blokkolás elkerüléséhez!
        # Renderen ehhez 'xvfb-run python app.py' indítás kell.
        browser = await p.chromium.launch(
            headless=False, 
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--use-gl=swiftshader', 
                '--window-size=1280,720'
            ]
        )
        
        context = await browser.new_context(
            locale="de-DE",
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
        )

        # Lopakodó mód: töröljük a webdriver nyomait
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Sütik betöltése (Geo-fix de)
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

        # Hálózati forgalom figyelése
        def handle_request(req):
            url_low = req.url.lower()
            if any(x in url_low for x in ["m3u8", "playlist", "manifest", "master"]):
                if req.url not in hits:
                    hits.append(req.url)
                    dlog(f"🎯 TALÁLAT: {req.url[:70]}...")
                    if req.url not in last_hits[target_url]:
                        last_hits[target_url].append(req.url)

        page.on("request", handle_request)

        try:
            dlog(f"📡 Navigálás: {target_url}")
            # A networkidle megvárja, amíg a háttérfolyamatok lecsillapodnak
            await page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            dlog("🔄 Kezdem a folyamatos gombnyomkodást...")
            
            while len(hits) == 0:
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                if elapsed > max_timeout:
                    dlog(f"⏱️ IDŐTÚLLÉPÉS ({max_timeout}s). Feladom.")
                    break

                # --- 1. COOKIE GOMBOK ---
                cookie_selectors = [
                    "button:has-text('Alle akzeptieren')",
                    "button:has-text('Zustimmen')",
                    "button:has-text('Akzeptieren')",
                    "#cmp-welcome-confirm-all"
                ]
                for sel in cookie_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=400):
                            await btn.click(force=True)
                            dlog(f"[{elapsed}s] 🖱️ Cookie leütve!")
                    except: pass

                # --- 2. PLAY GOMB ---
                try:
                    play_btn = page.locator("[data-testid='play-button'], button:has-text('Abspielen')").first
                    if await play_btn.is_visible(timeout=400):
                        await play_btn.click(force=True)
                        dlog(f"[{elapsed}s] ▶️ Play megnyomva!")
                except: pass

                # Rövid szünet a ciklusban a CPU kímélése érdekében
                await asyncio.sleep(2)

            if hits:
                dlog(f"✨ SIKER! {len(hits)} link begyűjtve.")

        except Exception as e:
            dlog(f"❌ HIBA A FOLYAMATBAN: {str(e)}")
        finally:
            dlog("🧹 Böngésző bezárása.")
            await browser.close()
    
    return hits

# --- FLASK ÚTVONALAK ---

@app.route('/')
def index():
    return "JOYN SNIFFER MŰKÖDIK. Használd: /web?url=... vagy /scrape?url=..."

@app.route('/web')
def web_view():
    """Böngészős monitor felület"""
    url = request.args.get('url')
    if not url: return "Hiba: Adj meg egy URL-t a böngészőben! (/web?url=...)", 400

    if url not in last_hits or not last_hits[url]:
        last_hits[url] = []
        dlog(f"WEB-KÉRÉS INDÍTVA: {url}")
        asyncio.get_event_loop().create_task(run_sniffer(url))
    
    return render_template_string(HTML_TEMPLATE, url=url, links=last_hits[url])

@app.route('/scrape', methods=['GET', 'POST'])
def scrape_api():
    """API végpont JSON válaszhoz"""
    user_cookies = []
    url = None

    if request.method == 'POST':
        data = request.get_json(silent=True)
        if data:
            url = data.get('url')
            user_cookies = data.get('cookies', [])
    else:
        url = request.args.get('url')

    if not url: 
        return jsonify({"status": "error", "message": "Nincs URL"}), 400
    
    dlog(f"API-KÉRÉS ({request.method}): {url}")
    
    # Új loop az API híváshoz, hogy megvárja a végét
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(run_sniffer(url, cookies=user_cookies))
        return jsonify({"status": "success", "hits": results})
    finally:
        loop.close()

# --- HTML SABLON ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Joyn Monitor</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { background: #000; color: #00ff41; font-family: monospace; padding: 20px; }
        .box { border: 1px solid #00ff41; padding: 20px; border-radius: 5px; background: #050505; }
        .hit { background: #111; border: 1px solid #333; padding: 10px; margin: 10px 0; word-break: break-all; font-size: 11px; border-left: 4px solid #00ff41; }
        .loading { color: #ffcc00; animation: blink 1s infinite; font-weight: bold; }
        @keyframes blink { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }
    </style>
</head>
<body>
    <div class="box">
        <h2>🛰️ JOYN TRAFFIC SNIFFER (XVFB)</h2>
        <p>Target: {{ url }}</p>
        <hr style="border-color: #222;">
        {% if links %}
            <p>✅ TALÁLT STREAMEK:</p>
            {% for link in links %}
                <div class="hit">{{ link }}</div>
            {% endfor %}
        {% else %}
            <p class="loading">📡 KERESÉS ÉS GOMBNYOMKODÁS... VÁRJ...</p>
            <p style="font-size: 0.8em; color: #666;">A szerver éppen próbálja elindítani a lejátszót Frankfurtban.</p>
        {% endif %}
    </div>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    dlog(f"Szerver indul a {port} porton...")
    app.run(host='0.0.0.0', port=port)
