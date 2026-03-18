import asyncio
import nest_asyncio
import os
import logging
from flask import Flask, request, jsonify, render_template_string
from playwright.async_api import async_playwright

# Flask és Playwright összeférhetőség javítása
nest_asyncio.apply()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

async def run_joyn_sniffer(target_url):
    captured_links = []
    async with async_playwright() as p:
        # Docker-specifikus indítási paraméterek
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                '--no-sandbox', 
                '--disable-setuid-sandbox', 
                '--disable-dev-shm-usage',
                '--disable-http2'
            ]
        )
        
        # Német környezet imitálása (fontos a Joyn-nak)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="de-DE",
            timezone_id="Europe/Berlin"
        )
        
        page = await context.new_page()

        # Hálózati forgalom figyelése (m3u8 és iocproactor szűrés)
        async def handle_request(req):
            url = req.url.lower()
            if any(x in url for x in ["m3u8", "iocproactor", "playback-ticket", "manifest"]):
                captured_links.append({"url": req.url, "method": req.method})

        page.on("request", handle_request)

        try:
            # Betöltés indítása
            await page.goto(target_url, wait_until="commit", timeout=60000)
            
            # Süti ablak kezelése (ha blokkolná a forgalmat)
            try:
                cookie_btn = page.locator('button:has-text("Akzeptieren"), button:has-text("Alle akzeptieren")')
                if await cookie_btn.is_visible(timeout=5000):
                    await cookie_btn.click()
            except:
                pass

            # Várakozás a háttérben futó stream kérésekre
            # A Joyn-nak kell némi idő, mire legenerálja a ticketet
            await asyncio.sleep(25) 

        except Exception as e:
            logging.error(f"Hiba a sniffer futása alatt: {e}")
        finally:
            await browser.close()
            
    return captured_links

# 1. JSON VÉGPONT (Helyi Python scriptnek vagy API-nak)
@app.route('/scrape')
def scrape():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "Nincs URL megadva"}), 400
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        hits = loop.run_until_complete(run_joyn_sniffer(url))
        unique_hits = list({v['url']:v for v in hits}.values())
        return jsonify({"status": "success", "hits": unique_hits})
    finally:
        loop.close()

# 2. WEB VÉGPONT (Böngészőben való megtekintéshez)
@app.route('/web')
def web_scrape():
    url = request.args.get('url')
    if not url:
        return "<h2>Hiba: Adj meg egy URL-t! Példa: /web?url=https://joyn.de/...</h2>", 400
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        hits = loop.run_until_complete(run_joyn_sniffer(url))
        unique_hits = list({v['url']:v for v in hits}.values())
        
        html_template = """
        <!DOCTYPE html>
        <html lang="hu">
        <head>
            <meta charset="UTF-8">
            <title>Joyn Link Sniffer</title>
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f0f0f; color: #e0e0e0; padding: 30px; }
                .container { max-width: 1000px; margin: auto; background: #1a1a1a; padding: 20px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
                h1 { color: #ff5a00; border-bottom: 2px solid #333; padding-bottom: 10px; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; table-layout: fixed; }
                th, td { border: 1px solid #333; padding: 12px; text-align: left; overflow-wrap: break-word; }
                th { background-color: #252525; color: #ff5a00; }
                tr:hover { background-color: #222; }
                .copy-btn { background: #ff5a00; color: white; border: none; padding: 8px 12px; cursor: pointer; border-radius: 5px; font-weight: bold; }
                .copy-btn:active { background: #cc4900; }
                .m3u8-label { color: #4caf50; font-weight: bold; }
                .ticket-label { color: #2196f3; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Talált Stream Linkek</h1>
                <p>Forrás: <i>{{ target }}</i></p>
                {% if hits %}
                <table>
                    <thead>
                        <tr>
                            <th style="width: 20%;">Típus</th>
                            <th style="width: 65%;">URL</th>
                            <th style="width: 15%;">Művelet</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for hit in hits %}
                        <tr>
                            <td>
                                <span class="{{ 'm3u8-label' if 'm3u8' in hit.url else 'ticket-label' }}">
                                    {{ '🎬 M3U8 (Master)' if 'm3u8' in hit.url else '🔑 PLAYBACK TICKET' }}
                                </span>
                            </td>
                            <td style="font-size: 11px; color: #bbb;">{{ hit.url }}</td>
                            <td><button class="copy-btn" onclick="navigator.clipboard.writeText('{{ hit.url }}'); alert('Másolva!')">Másolás</button></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <div style="padding: 40px; text-align: center;">
                    <p>❌ Nem találtam releváns linket. Ellenőrizd, hogy a tartalom ingyenes-e!</p>
                </div>
                {% endif %}
                <br>
                <a href="/web?url={{ target }}" style="color: #ff5a00; text-decoration: none;">🔄 Újrafuttatás</a>
            </div>
        </body>
        </html>
        """
        return render_template_string(html_template, hits=unique_hits, target=url)
    finally:
        loop.close()

# Alapértelmezett főoldal
@app.route('/')
def index():
    return "<h1>Joyn Sniffer Docker Server Aktív</h1><p>Használd a /web?url=... végpontot!</p>"

if __name__ == '__main__':
    # Render PORT beállítás
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
