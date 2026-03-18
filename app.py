import asyncio
import nest_asyncio
import os
import json
from flask import Flask, request, render_template_string, jsonify
from playwright.async_api import async_playwright

# Engedélyezzük az egymásba ágyazott eseményhurkokat (Render/Flask miatt)
nest_asyncio.apply()

app = Flask(__name__)

# Memória a /web nézethez (URL -> talált linkek listája)
last_hits = {}

async def run_sniffer(target_url, cookies=None, wait_time=45):
    """Közös motor a böngészéshez és linkgyűjtéshez"""
    hits = []
    async with async_playwright() as p:
        # Böngésző indítása speciális flag-ekkel a blokkolás elkerülésére
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                '--no-sandbox', 
                '--disable-setuid-sandbox', 
                '--disable-blink-features=AutomationControlled'
            ]
        )
        
        context = await browser.new_context(
            locale="de-DE",
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
        )

        # Sütik előkészítése és Geo-fix
        if cookies:
            cleaned_cookies = []
            for cookie in cookies:
                c = cookie.copy()
                if c.get('name') == 'geoLocation':
                    c['value'] = 'de'
                # Playwright inkompatibilis mezők eltávolítása
                c.pop('hostOnly', None)
                c.pop('storeId', None)
                cleaned_cookies.append(c)
            
            await context.add_cookies(cleaned_cookies)
            print(f"[DEBUG] {len(cleaned_cookies)} süti betöltve.")

        page = await context.new_page()

        # Hálózati forgalom figyelése (Request alapon, hogy gyorsabb legyen)
        def handle_request(req):
            url_low = req.url.lower()
            # Bővített kulcsszavak a biztosabb találathoz
            if any(x in url_low for x in ["m3u8", "playlist", "playback", "manifest", "master"]):
                if req.url not in hits:
                    hits.append(req.url)
                    # Frissítjük a globális tárolót is
                    if target_url in last_hits:
                        if req.url not in last_hits[target_url]:
                            last_hits[target_url].append(req.url)

        page.on("request", handle_request)

        try:
            print(f"[*] Navigálás: {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

            # --- 1. COOKIE GOMB NYOMKODÁSA (Német nyelven) ---
            try:
                # Többféle lehetséges felirat vagy azonosító
                cookie_selectors = [
                    "button:has-text('Alle akzeptieren')",
                    "button:has-text('Zustimmen')",
                    "button:has-text('Akzeptieren')",
                    "#cmp-welcome-confirm-all",
                    ".sc-gsDKAQ"
                ]
                
                for selector in cookie_selectors:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=5000):
                        await btn.click()
                        print("[+] Cookie ablak sikeresen lezárva.")
                        break
            except:
                print("[!] Cookie gomb nem jelent meg (vagy a sütik már megoldották).")

            # --- 2. PLAY GOMB (Ha szükséges az indításhoz) ---
            await asyncio.sleep(3)
            try:
                play_btn = page.locator("[data-testid='play-button'], .play-button, button:has-text('Abspielen')").first
                if await play_btn.is_visible(timeout=3000):
                    await play_btn.click()
                    print("[+] Play gomb megnyomva.")
            except:
                pass

            # Várakozás a streamekre (reklámok és betöltés ideje)
            await asyncio.sleep(wait_time) 

        except Exception as e:
            print(f"[HIBA]: {e}")
        finally:
            await browser.close()
    
    return hits

# --- FLASK ÚTVONALAK ---

@app.route('/web')
def web_view():
    url = request.args.get('url')
    if not url: return "Adj meg egy URL-t: /web?url=https://...", 400

    if url not in last_hits:
        last_hits[url] = []
        # Háttérben indítjuk a keresőt
        asyncio.get_event_loop().create_task(run_sniffer(url))
        return render_template_string(HTML_TEMPLATE, url=url, links=[])

    return render_template_string(HTML_TEMPLATE, url=url, links=last_hits[url])

@app.route('/scrape', methods=['GET', 'POST'])
def scrape_api():
    user_cookies = []
    if request.method == 'POST':
        data = request.get_json()
        if not data: return jsonify({"error": "Nincs JSON"}), 400
        url = data.get('url')
        user_cookies = data.get('cookies', [])
    else:
        url = request.args.get('url')

    if not url: return jsonify({"status": "error", "message": "Nincs URL"}), 400
    
    # Új loop a szinkron API híváshoz
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
    return "JOYN SNIFFER ONLINE. Használd a /web?url=... útvonalat."

# --- HTML SABLON ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Joyn Traffic Monitor</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { background: #0a0a0a; color: #00ff41; font-family: 'Courier New', monospace; padding: 30px; line-height: 1.6; }
        .container { max-width: 1000px; margin: 0 auto; border: 1px solid #333; padding: 20px; border-radius: 8px; }
        h2 { border-bottom: 2px solid #00ff41; padding-bottom: 10px; color: #fff; }
        .hit { background: #1a1a1a; border-left: 4px solid #00ff41; padding: 15px; margin: 10px 0; word-break: break-all; font-size: 12px; }
        .loading { color: #ffcc00; font-weight: bold; animation: blink 1.5s infinite; }
        .url-display { color: #888; font-style: italic; margin-bottom: 20px; }
        @keyframes blink { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }
    </style>
</head>
<body>
    <div class="container">
        <h2>🛰️ JOYN TRAFFIC SNIFFER</h2>
        <div class="url-display">Target: {{ url }}</div>
        
        {% if links %}
            <p>✅ Talált linkek ({{ links|length }} db):</p>
            {% for link in links %}
                <div class="hit"><b>[M3U8/STREAM]:</b> {{ link }}</div>
            {% endfor %}
        {% else %}
            <p class="loading">📡 KERESÉS FOLYAMATBAN... (Cookie-k elfogadása, reklámok megvárása...)</p>
            <p style="font-size: 0.8em; color: #555;">Az oldal 5 másodpercenként frissül. Ha 1 perc után sincs semmi, ellenőrizd a linket.</p>
        {% endif %}
    </div>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
