# 1. Hivatalos Microsoft Playwright kép használata Python 3.11-gyel (stabilabb, mint a 3.14)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# 2. Munkakönyvtár beállítása a konténeren belül
WORKDIR /app

# 3. Függőségek másolása (hogy a cache-elés hatékony legyen)
COPY requirements.txt .

# 4. Python csomagok telepítése
RUN pip install --no-cache-dir -r requirements.txt

# 5. A Chromium böngésző és a szükséges rendszerelemek telepítése
# A Dockerben ez az egyetlen módja, hogy biztosan meglegyen a böngésző
RUN playwright install chromium
RUN playwright install-deps chromium

# 6. A teljes forráskód másolása a konténerbe
COPY . .

# 7. Környezeti változó a Portnak (a Rendernek 10000 kell alapból)
ENV PORT=10000
EXPOSE 10000

# 8. Az alkalmazás indítása
CMD ["python", "app.py"]
