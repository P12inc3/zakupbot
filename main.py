import time
import traceback
import re
import logging
import requests
from datetime import datetime, timedelta, timezone

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# НАСТРОЙКИ
TOKEN = "5526925742:AAEnEEnlGcnzqcWIVFFeQsniVPDzImuUhvg"
CHAT_IDS = ["696601899"]
URL = (
    "https://zakup.sk.kz/#/ext?tabs=advert&q=\u042d\u043a\u0441\u043f\u0435\u0440\u0442\u0438\u0437&adst=PUBLISHED&lst=PUBLISHED&page=1"
)
WAIT_SELECTOR = "div.block-footer"  # Блок, где ищем "Найдено"

CHECK_INTERVAL = 300
MAX_CONSECUTIVE_ERRORS = 3
DRIVER_REFRESH_HOURS = 6

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)


# TELEGRAM

def tg_send(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
            if r.status_code != 200:
                logging.error("TG %s: %s", r.status_code, r.text)
        except Exception as exc:
            logging.error("TG error: %s", exc)


# SELENIUM

def make_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)


# ПАРСИНГ
_RE = re.compile(r"\u041d\u0430\u0439\u0434\u0435\u043d\u043e\\s+(\\d+)")

def parse_count(text):
    match = _RE.search(text)
    return int(match.group(1)) if match else None

def fetch_count(driver):
    driver.get(URL)
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, WAIT_SELECTOR)))
    time.sleep(2)
    txt = driver.execute_script("return document.body.innerText")
    logging.debug("Fetched body text: %s", txt[:1000])
    return parse_count(txt)


# ОСНОВНОЙ ЦИКЛ

def main():
    driver = make_driver()
    last_count = None
    consecutive_err = 0
    tg_send("✅ Монитор запущен.")

    try:
        while True:
            try:
                count = fetch_count(driver)
                if count is None:
                    raise ValueError("⚠️ Не найдено число лотов. Возможно, изменилась структура страницы.")

                if last_count is None:
                    last_count = count
                    logging.info("Initial count: %d", count)
                elif count != last_count:
                    diff = count - last_count
                    msg = f"📢 Изменение: {last_count} → {count} (Δ {diff:+})"
                    tg_send(msg)
                    logging.info(msg)
                    last_count = count
                else:
                    logging.info("Без изменений (%d)", count)

                consecutive_err = 0  # сброс ошибок

            except Exception as e:
                consecutive_err += 1
                logging.warning("Ошибка (%d): %s", consecutive_err, str(e))
                logging.debug(traceback.format_exc())
                tg_send(f"❌ Ошибка при получении данных: {e}")

                if consecutive_err >= MAX_CONSECUTIVE_ERRORS:
                    logging.info("🔁 Перезапуск драйвера из-за ошибок")
                    driver.quit()
                    driver = make_driver()
                    consecutive_err = 0

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logging.info("Остановлено пользователем")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()