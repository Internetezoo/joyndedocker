import time
import os
from playwright.sync_api import sync_playwright

TARGET_URL = "https://www.joyn.de/play/serien/die-waltons/1-1-das-findelkind"

def brute_force_until_m3u8():
    with sync_playwright() as p:
        # A Playwright maga indítja a böngészőt a Dockerben
        browser = p.chromium.launch(headless=True, args=[
            "--lang=de-DE",
            "--no-sandbox", 
            "--disable-setuid-sandbox",
            "--mute-audio"
        ])
        
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
        page = context.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})

        found_data = {"m3u8": None}

        def handle_response(response):
            if "playlist" in response.url and response.request.method == "POST":
                if response.status == 200:
                    try:
                        json_data = response.json()
                        url = json_data.get("manifestUrl")
                        if url:
                            found_data["m3u8"] = url
                            print(f"\n[!!!] SIKER: {url}")
                    except: pass

        page.on("response", handle_response)
        print(f"[*] Navigálás: {TARGET_URL}")
        
        try:
            page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            
            # Ciklus a gombok kezeléséhez (maradhat az eredeti logikád)
            start_time = time.time()
            while not found_data["m3u8"]:
                # ... (Gombnyomogató logika, amit írtál) ...
                
                if time.time() - start_time > 300: break
                time.sleep(2)

        finally:
            browser.close()

if __name__ == "__main__":
    brute_force_until_m3u8()
