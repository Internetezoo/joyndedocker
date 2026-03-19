# 1. Hivatalos Playwright kép használata (tartalmazza a Python-t és a böngésző függőségeket)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# 2. Munkakönyvtár létrehozása a konténeren belül
WORKDIR /app

# 3. Környezeti változók beállítása a stabilabb futáshoz
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 4. Függőségek másolása és telepítése
# A requirements.txt-ben legyen benne: flask, playwright, gunicorn
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. A böngésző binárisok telepítése (csak a Chromium-ot telepítjük a helytakarékosság miatt)
RUN playwright install chromium

# 6. A teljes forráskód másolása a munkakönyvtárba
COPY . .

# 7. Port expose (Render alapértelmezett portja)
EXPOSE 10000

# 8. Indítás Gunicorn-nal (app.py fájlban lévő app objektum indítása)
# A --timeout 0 fontos, mert a Playwright műveletek hosszú ideig tarthatnak
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "0", "app:app"]
