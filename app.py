import asyncio
import nest_asyncio
import os
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

nest_asyncio.apply()
app = Flask(__name__)

async def run_joyn_sniffer(target_url):
    captured_links = []
    async with async_playwright() as p:
        # A --disable-http2 segíthet, hogy a proxy-k ne kavarjanak be
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-http2']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # MINDEN kérést figyelünk, ami tartalmazza a kulcsszavainkat
        page.on("request", lambda request: (
            captured_links.append({"url": request.url, "method": request.method})
            if any(x in request.url.lower() for x in ["m3u8", "iocproactor", "playback", "master.m3u8", "index.m3u8"])
            else None
        ))

        try:
            # Csak a DOM betöltéséig várunk, nem a teljes hálózati nyugalomig
            await page.goto(target_url, wait_until="commit", timeout=60000)
            
            # Várunk fixen, amíg a scriptek a háttérben elkezdenek "beszélni"
            # A Joyn-nak kell kb 15-20 másodperc, mire az iocproactor felbukkan
            await asyncio.sleep(30) 

        except Exception as e:
            print(f"Hiba a betöltés alatt: {e}")
        finally:
            await browser.close()
            
    return captured_links

@app.route('/scrape')
def scrape():
    url = request.args.get('url')
    if not url: return jsonify({"error": "No URL"}), 400
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        hits = loop.run_until_complete(run_joyn_sniffer(url))
        # Kiszedjük a duplikációkat, hogy tisztább legyen az eredmény
        unique_hits = list({v['url']:v for v in hits}.values())
        return jsonify({"status": "success", "hits": unique_hits})
    finally:
        loop.close()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
