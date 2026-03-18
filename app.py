import asyncio
import nest_asyncio
import os
import json
from flask import Flask, request, render_template_string, jsonify
from playwright.async_api import async_playwright

nest_asyncio.apply()
app = Flask(__name__)

# Memória a /web nézethez
last_hits = {}

async def run_sniffer(target_url, cookies=None, wait_time=45):
    """Közös motor a böngészéshez és linkgyűjtéshez"""
    hits = []
    async with async_playwright() as p:
        # Böngésző indítása (headless módban a Render miatt)
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            locale="de-DE",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
        )

        # Sütik betöltése és Geo-fix (hu -> de)
        if cookies:
            for cookie in cookies:
                if cookie.get('name') == 'geoLocation':
                    cookie['value'] = 'de'
                # Playwright-nak nem kell a 'hostOnly' és 'storeId' mező
                cookie.pop('hostOnly', None)
                cookie.pop('storeId', None)
            
            await context.add_cookies(cookies)
            print(f"DEBUG: {len(cookies)} süti betöltve.")

        page = await context.new_page()

        # Hálózati forgalom figyelése
        def handle_request(req):
            url_low = req.url.lower()
            if any(x in url_low for x in ["m3u8", "iocproactor", "playback", "manifest"]):
                if req.url not in hits:
                    hits.append(req.url)
                    # Frissítjük a globális tárolót is a /web számára
                    if target_url in last_hits:
                        if req.url not in last_hits[target_url]:
                            last_hits[target_url].append(req.url)

        page.on("request", handle_request)

        try:
            # Oldal megnyitása
            await page.goto(target_url, wait_until="commit", timeout=60000)
            # Várunk, hogy a lejátszó elinduljon és a linkek felbukkanjanak
            await asyncio.sleep(wait_time) 
        except Exception as e:
            print(f"Hiba a böngészés alatt: {e}")
        finally:
            await browser.close()
    
    return hits

# --- 1. /WEB: ÉLŐ MONITOR (Böngészőbe) ---
@app.route('/web')
def web_view():
    url = request.args.get('url')
    if not url: return "Adj meg egy URL-t a böngészőben: /web?url=...", 400

    if url not in last_hits:
        last_hits[url] = []
        # Háttérben indítjuk, hogy ne blokkolja a Flask-ot
        asyncio.get_event_loop().create_task(run_sniffer(url))
        return render_template_string(HTML_TEMPLATE, url=url, links=[])

    return render_template_string(HTML_TEMPLATE, url=url, links=last_hits[url])

# --- 2. /SCRAPE: PYTHON API (JSON + Sütik) ---
@app.route('/scrape', methods=['GET', 'POST'])
def scrape_api():
    user_cookies = []
    
    if request.method == 'POST':
        # Ha JSON érkezik a local.py-tól
        data = request.get_json()
        if not data: return jsonify({"error": "Nincs JSON adat"}), 400
        url = data.get('url')
        user_cookies = data.get('cookies', [])
    else:
        # Ha csak sima GET (böngészőből teszteled)
        url = request.args.get('url')

    if not url: return jsonify({"status": "error", "message": "Nincs URL"}), 400
    
    # Itt megvárjuk az eredményt (szinkron hívás a local.py-nak)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(run_sniffer(url, cookies=user_cookies, wait_time=40))
        return jsonify({
            "status": "success",
            "hits": [{"url": h} for h in results]
        })
    finally:
        loop.close()

@app.route('/')
def index():
    return "Szerver fut. Használd a /web vagy /scrape útvonalakat."

# HTML Kinézet a /web-hez
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Joyn Monitor</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { background: #000; color: #0f0; font-family: monospace; padding: 20px; }
        .hit { background: #111; border: 1px solid #0f0; padding: 10px; margin: 5px 0; word-break: break-all; font-size: 11px; }
        .loading { color: orange; animation: blink 1s infinite; }
        @keyframes blink { 0% {opacity:1} 50% {opacity:0} 100% {opacity:1} }
    </style>
</head>
<body>
    <h2>🛰️ JOYN TRAFFIC SNIFFER (FRANKFURT)</h2>
    <p>Target: {{ url }}</p>
    <hr>
    {% if links %}
        {% for link in links %}
            <div class="hit"><b>[FOUND]:</b> {{ link }}</div>
        {% endfor %}
    {% else %}
        <p class="loading">📡 KERESÉS... VÁRJ A REKLÁMOK UTÁNIG...</p>
    {% endif %}
</body>
</html>
"""

if __name__ == '__main__':
    # Render port kezelése
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
