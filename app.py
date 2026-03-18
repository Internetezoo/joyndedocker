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

# Memória a /web nézethez
last_hits = {}

def dlog(msg):
    """Egyedi debug log formátum időbélyeggel a Render konzolba"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [DEBUG] {msg}")
    sys.stdout.flush() # Azonnali kiírás a konzolra

async def run_sniffer(target_url, cookies=None, wait_time=45):
    hits = []
    dlog(f"🚀 Új keresés indítása: {target_url}")
    
    async with async_playwright() as p:
        dlog("🌐 Chromium indítása...")
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            locale="de-DE",
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
        )

        if cookies:
            cleaned_cookies = []
            for cookie in cookies:
                c = cookie.copy()
                if c.get('name') == 'geoLocation': c['value'] = 'de'
                c.pop('hostOnly', None)
                c.pop('storeId', None)
                cleaned_cookies.append(c)
            await context.add_cookies(cleaned_cookies)
            dlog(f"🍪 {len(cleaned_cookies)} süti sikeresen betöltve.")

        page = await context.new_page()

        def handle_request(req):
            url_low = req.url.lower()
            if any(x in url_low for x in ["m3u8", "playlist", "playback", "manifest", "master"]):
                if req.url not in hits:
                    hits.append(req.url)
                    dlog(f"🎯 TALÁLAT: {req.url[:80]}...") # Csak az elejét logoljuk, hogy ne legyen fal
                    if target_url in last_hits:
                        if req.url not in last_hits[target_url]:
                            last_hits[target_url].append(req.url)

        page.on("request", handle_request)

        try:
            dlog(f"📡 Navigálás az oldalra...")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            dlog(f"✅ Oldal betöltve (DOM).")

            # --- 1. COOKIE GOMB ---
            await asyncio.sleep(2)
            cookie_selectors = [
                "button:has-text('Alle akzeptieren')",
                "button:has-text('Zustimmen')",
                "button:has-text('Akzeptieren')",
                "#cmp-welcome-confirm-all"
            ]
            
            cookie_found = False
            for selector in cookie_selectors:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    dlog(f"🖱️  Cookie gomb megnyomva ({selector})")
                    cookie_found = True
                    break
            
            if not cookie_found:
                dlog("❓ Cookie ablak nem észlelhető (lehet, hogy a sütik már elnyomták).")

            # --- 2. PLAY GOMB ---
            await asyncio.sleep(3)
            try:
                play_btn = page.locator("[data-testid='play-button'], button:has-text('Abspielen')").first
                if await play_btn.is_visible(timeout=3000):
                    await play_btn.click()
                    dlog("▶️  Play gomb megnyomva.")
            except:
                dlog("ℹ️ Play gomb nem látható, valószínűleg már fut a lejátszó.")

            dlog(f"⏳ Várakozás a hálózati forgalomra ({wait_time}s)...")
            await asyncio.sleep(wait_time) 

        except Exception as e:
            dlog(f"❌ HIBA: {str(e)}")
        finally:
            dlog("🧹 Böngésző bezárása, folyamat vége.")
            await browser.close()
    
    return hits

# --- FLASK ÚTVONALAK ---

@app.route('/web')
def web_view():
    url = request.args.get('url')
    if not url: return "Adj meg egy URL-t!", 400

    if url not in last_hits:
        last_hits[url] = []
        dlog(f"WEB: Kérés érkezett ide: {url}")
        asyncio.get_event_loop().create_task(run_sniffer(url))
    
    return render_template_string(HTML_TEMPLATE, url=url, links=last_hits[url])

@app.route('/scrape', methods=['GET', 'POST'])
def scrape_api():
    user_cookies = []
    if request.method == 'POST':
        data = request.get_json()
        url = data.get('url')
        user_cookies = data.get('cookies', [])
        dlog(f"API: POST kérés érkezett - {url}")
    else:
        url = request.args.get('url')
        dlog(f"API: GET kérés érkezett - {url}")

    if not url: return jsonify({"status": "error", "message": "Nincs URL"}), 400
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(run_sniffer(url, cookies=user_cookies, wait_time=40))
        dlog(f"API: Küldöm az eredményeket ({len(results)} db hit).")
        return jsonify({"status": "success", "hits": [{"url": h} for h in results]})
    finally:
        loop.close()

@app.route('/')
def index():
    dlog("Ping érkezett a főoldalra.")
    return "JOYN SNIFFER ONLINE."

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Joyn Monitor</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { background: #000; color: #0f0; font-family: monospace; padding: 20px; }
        .container { border: 1px solid #0f0; padding: 20px; }
        .hit { background: #111; border: 1px solid #444; padding: 10px; margin: 10px 0; word-break: break-all; color: #00ff41; }
        .status { color: #ffcc00; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🛰️ JOYN SNIFFER LOGS</h2>
        <p>Target: {{ url }}</p>
        <hr>
        {% if links %}
            <p>✅ Talált linkek:</p>
            {% for link in links %}
                <div class="hit">{{ link }}</div>
            {% endfor %}
        {% else %}
            <p class="status">📡 KERESÉS FOLYAMATBAN... Ellenőrizd a Render konzolt a részletekért!</p>
        {% endif %}
    </div>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    dlog(f"Szerver indul a {port} porton...")
    app.run(host='0.0.0.0', port=port)
