# 1. Hivatalos Microsoft Playwright kép (Ubuntu Jammy alapú)
# Ez tartalmazza a legtöbb szükséges függőséget alapból.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# 2. Xvfb telepítése (Virtuális kijelző a non-headless módhoz)
RUN apt-get update && apt-get install -y \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 3. Munkakönyvtár létrehozása
WORKDIR /app

# 4. Függőségek másolása és telepítése
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Böngésző telepítése (biztonsági okokból lefuttatjuk)
RUN playwright install chromium

# 6. Jogosultságok és ideiglenes könyvtár fixálása az Xvfb-nek
# Ez megelőzi a "Could not create lock file" hibákat
RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# 7. Forráskód másolása
COPY . .

# 8. Port beállítása (Render alapértelmezett 10000)
ENV PORT=10000
EXPOSE 10000

# 9. A JAVÍTOTT INDÍTÁS
# Az "exec" formátumot (szögletes zárójel) használjuk, 
# így a paraméterek nem csúsznak szét, és nem jön a "0: not found" hiba.
CMD ["xvfb-run", "-a", "python", "app.py"]
