# 1. Hivatalos Microsoft Playwright kép (Ubuntu Jammy alapú)
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# 2. Xvfb és kiegészítő függőségek telepítése (EZ HIÁNYZOTT)
RUN apt-get update && apt-get install -y \
    xvfb \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# 3. Munkakönyvtár beállítása
WORKDIR /app

# 4. Függőségek másolása
COPY requirements.txt .

# 5. Python csomagok telepítése
RUN pip install --no-cache-dir -r requirements.txt

# 6. Chromium telepítése (a Microsoft képben benne van, de biztosra megyünk)
RUN playwright install chromium

# 7. Forráskód másolása
COPY . .

# 8. Render Port beállítása
ENV PORT=10000
EXPOSE 10000

# 9. Indítás xvfb-n keresztül
# Megjegyzés: Ha a Render felületén a "Docker Command"-ba beírod az xvfb-run-t, 
# az felülbírálja ezt, de jobb, ha itt is benne van alapértelmezettnek.
CMD ["xvfb-run", "--server-args=-screen 0 1280x720x24", "python", "app.py"]
