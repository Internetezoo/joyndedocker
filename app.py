import asyncio
import nest_asyncio
import os
from flask import Flask, request, render_template_string, jsonify
from playwright.async_api import async_playwright

nest_asyncio.apply()
app = Flask(__name__)

# Memóriában tároljuk a legutóbbi találatokat, hogy a /web lássa
last_hits = {}

async def run_sniffer(target_url, wait_time=45):
    """Ez a közös motor, ami a háttérben böngészik."""
    hits = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            locale="de-DE",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Elrejtjük, hogy botok vagyunk
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Figyeljük a hálózati kéréseket
        def handle_request(req):
            url_low = req.url.lower()
            if any(x in url_low for x in ["m3u8", "iocproactor", "playback", "manifest"]):
                if req.url not in hits:
                    hits.append(req.url)
                    # Ha a /web-nek is kell, ide is betesszük
                    if target_url in last_hits:
                        if req.url not in last_hits[target_url]:
                            last_hits[target_url].append(req.url)

        page.on("request", handle_request)

        try:
            await page.goto(target_url, wait_until="commit")
            await asyncio.sleep(wait_time) 
        except:
            pass
        finally:
            await browser.close()
    return hits

# --- 1. WEB: ÉLŐ MONITOR NÉZET ---
@app.route('/web')
def web_view():
    url = request.args.get('url')
    if not url: return "Adj meg egy URL-t!", 400

    if url not in last_hits:
        last_hits[url] = []
        # Elindítjuk a háttérben a figyelést
        asyncio.get_event_loop().create_task(run_sniffer(url))
        return render_template_string(HTML_TEMPLATE, url=url, links=[])

    return render_template_string(HTML_TEMPLATE, url=url, links=last_hits[url])

# --- 2. SCRAPE: PYTHON JSON VÉGPONT ---
@app.route('/scrape')
def scrape_api():
    url = request.args.get('url')
    if not url: return jsonify({"status": "error", "message": "No URL"}), 400
    
    # Itt megvárjuk a végét, mert a Python script választ vár
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(run_sniffer(url, wait_time=30))
        return jsonify({
            "status": "success",
            "target": url,
            "hits": [{"url": h} for h in results]
        })
    finally:
        loop.close()

# Alapértelmezett oldal útmutatóval
@app.route('/')
def index():
    return """
    <body style="font-family:sans-serif; padding:50px;">
        <h1>Joyn Sniffer Server Aktív</h1>
        <p>Böngészéshez: <code>/web?url=...</code></p>
        <p>Pythonhoz: <code>/scrape?url=...</code></p>
    </body>
    """

# HTML sablon a monitorhoz
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Joyn Monitor</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { background: #0a0a0a; color: #00ff41; font-family: 'Courier New', monospace; padding: 20px; }
        .hit { background: #111; border: 1px solid #00ff41; padding: 10px; margin: 5px 0; word-break: break-all; }
        .scan { color: orange; font-weight: bold; }
    </style>
</head>
<body>
    <h2>[🛰️ SCANNING] {{ url }}</h2>
    <hr>
    {% if links %}
        {% for link in links %}
            <div class="hit"><b>[FOUND]:</b> {{ link }}</div>
        {% endfor %}
    {% else %}
        <p class="scan">>>> INITIALIZING CHROME IN FRANKFURT... PLEASE WAIT...</p>
    {% endif %}
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
