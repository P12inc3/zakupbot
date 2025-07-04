FROM python:3.12-slim

# ── Устанавливаем Chromium и Chromedriver той же версии ──
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils && \
    rm -rf /var/lib/apt/lists/*

# ── Устанавливаем Python-зависимости ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Копируем исходники ──
WORKDIR /app
COPY . /app

# ── Пути для Selenium ──
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# ── Точка входа ──
CMD ["python", "main.py"]
