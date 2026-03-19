FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Függőségek
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

# Létrehozzuk a videók mappáját
RUN mkdir -p /app/videos && chmod 777 /app/videos

COPY . .

ENV PORT=10000
EXPOSE 10000

# Egyszerű indítás, nincs szükség xvfb-run-ra
CMD ["python", "app.py"]
