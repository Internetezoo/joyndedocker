# Hivatalos Playwright kép, amiben benne van a Python és a böngésző függőségek is
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Munkakönyvtár beállítása
WORKDIR /app

# Függőségek másolása és telepítése
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Böngészők telepítése (ha a képben nem lenne elég)
RUN playwright install chromium

# Kód másolása
COPY . .

# Indítás
CMD ["python", "app.py"]
