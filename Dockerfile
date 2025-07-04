FROM python:3.12-slim

# Установка зависимостей
RUN apt-get update && apt-get install -y \
    chromium-driver \
    chromium \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libxss1 \
    libgtk-3-0 \
    libdrm2 \
    libgbm1 \
    wget \
    curl \
    unzip \
    && apt-get clean

ENV PATH="/usr/lib/chromium:/usr/lib/chromium-browser:$PATH"
ENV CHROME_BIN="/usr/bin/chromium"
ENV CHROMEDRIVER_PATH="/usr/bin/chromedriver"

# Установка Python зависимостей
WORKDIR /app
COPY . /app
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD ["python", "main.py"]
