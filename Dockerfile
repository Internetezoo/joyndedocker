# 1. Alapkép (Playwright Jammy - stabil és tartalmazza a függőségek 90%-át)
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# 2. Xvfb telepítése (virtuális kijelző)
RUN apt-get update && apt-get install -y \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 3. Könyvtárak és jogosultságok fixálása (X11 lock fájl hiba ellen)
RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

WORKDIR /app

# 4. Függőségek
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

# 5. Kód másolása
COPY . .

# 6. Port beállítás
ENV PORT=10000
EXPOSE 10000

# 7. A STABIL INDÍTÁS (Exec formátum)
# Az '-a' (auto-servernum) megkeresi a szabad kijelzőt, 
# így nem kell kézzel megadni a '0'-át, ami a hibát okozta.
CMD ["xvfb-run", "-a", "python", "app.py"]
