import asyncio
import nest_asyncio
import logging
import os
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

# Ez kell, hogy a Flask és a Playwright ne akadjon össze
nest_asyncio.apply()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

async def run_joyn_sniffer(target_url):
    captured_links = []
    async with async_playwright() as p:
        # Dockerben a --no-sandbox kötelező!
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Elkapjuk a hálózati kéréseket (m3u8, iocproactor)
        async def handle_request(request):
            url = request.url
            if any(x in url.lower() for x in ["m3u8", "iocproactor", "playback", "manifest"]):
                captured_links.append({"url": url, "method": request.method})

        page.on("request", handle_request)

        try:
            await page.goto(target_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(10) # Várunk, hogy a videó elinduljon
        except Exception as e:
            logging.error(f"Hiba: {e}")
        finally:
            await browser.close()
    return captured_links

@app.route('/scrape', methods=['GET'])
def scrape():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "Nincs URL megadva"}), 400
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        hits = loop.run_until_complete(run_joyn_sniffer(url))
        return jsonify({"status": "success", "hits": hits})
    finally:
        loop.close()

# --- EZ A RÉSZ, AMIT KÉRDEZTÉL ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
