import time
import random
import logging
import re
import requests
from datetime import datetime, timedelta, timezone

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# ─────────────────────────────────────
# 🔧 НАСТРОЙКИ
# ─────────────────────────────────────
TOKEN = "ВАШ_ТГ_ТОКЕН"
CHAT_IDS = ["ВАШ_CHAT_ID"]

URL = (
    "https://zakup.sk.kz/#/ext?"
    "tabs=advert&q=Экспертиз&adst=PUBLISHED&lst=PUBLISHED&page=1"
)
WAIT_SELECTOR = "div.block-footer"             # где есть «Найдено …»

CHECK_INTERVAL = 300                           # 5 минут
JITTER_SECONDS = 30
MAX_CONSECUTIVE_ERRORS = 4
DRIVER_REFRESH_HOURS = 6
BACKOFF_STEP = 60
BACKOFF_MAX = 15 * 60
LOG_FILE = "monitor.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)

# ─────────────────────────────────────
# 📩 TELEGRAM
# ─────────────────────────────────────
def tg_send(text: str) -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
            if r.status_code != 200:
                logging.error("TG %s: %s", r.status_code, r.text)
        except Exception as exc:
            logging.error("TG error: %s", exc)

# ─────────────────────────────────────
# 🌐 SELENIUM
# ─────────────────────────────────────
def make_driver() -> webdriver.Chrome:
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    # chromedriver и chromium ставятся через apt, пути стандартные
    return webdriver.Chrome(
        service=Service("/usr/bin/chromedriver"),
        options=opts,
    )

# ─────────────────────────────────────
# 🔍 ПАРСИНГ
# ─────────────────────────────────────
_RE = re.compile(r"Найдено\s+(\d+)")

def parse_count(text: str) -> int | None:
    m = _RE.search(text)
    return int(m.group(1)) if m else None

def fetch_count(driver: webdriver.Chrome) -> int | None:
    driver.get(URL)
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, WAIT_SELECTOR))
    )
    time.sleep(2)                          # даём JS полностью прогрузиться
    txt = driver.execute_script("return document.body.innerText")
    return parse_count(txt)

# ─────────────────────────────────────
# 🔁 ОСНОВНОЙ ЦИКЛ
# ─────────────────────────────────────
def main() -> None:
    print("✅ main.py запущен")            # <-- диагноз старта
    driver = make_driver()
    print("✅ Драйвер создан")             # <-- диагноз

    driver_birth = datetime.now(tz=timezone.utc)
    last_count = None
    consecutive_err = 0
    backoff = 0
    sent_down_notice = False

    tg_send("✅ Мониторинг лотов запущен.")
    logging.info("Started monitor.")

    try:
        while True:
            start = time.time()

            # профилактический рестарт драйвера
            if datetime.now(tz=timezone.utc) - driver_birth > timedelta(hours=DRIVER_REFRESH_HOURS):
                logging.info("Refreshing Chrome driver.")
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = make_driver()
                driver_birth = datetime.now(tz=timezone.utc)

            try:
                count = fetch_count(driver)
                if count is None:
                    raise ValueError("Не найдено число лотов.")

                # сайт «ожил»
                if sent_down_notice:
                    tg_send("✅ Связь с zakup.sk.kz восстановлена.")
                    sent_down_notice = False

                consecutive_err = 0
                backoff = 0

                if last_count is None:
                    last_count = count
                    logging.info("Initial count: %d", count)
                elif count != last_count:
                    diff = count - last_count
                    arrow = "🔺" if diff > 0 else "🔻"
                    msg = f"{arrow} Лоты: {last_count} → {count} (Δ {diff:+})"
                    tg_send(msg)
                    logging.info(msg)
                    last_count = count
                else:
                    logging.info("Unchanged (%d).", count)

            except (TimeoutException, WebDriverException, Exception) as exc:
                consecutive_err += 1
                logging.warning("Fetch failed (%d): %s", consecutive_err, exc)
                if not sent_down_notice:
                    tg_send(f"⚠️ Проблема с zakup.sk.kz: {exc}")
                    sent_down_notice = True

                if consecutive_err >= MAX_CONSECUTIVE_ERRORS:
                    logging.error("Too many errors, restarting driver.")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = make_driver()
                    driver_birth = datetime.now(tz=timezone.utc)
                    consecutive_err = 0

                backoff = min(backoff + BACKOFF_STEP, BACKOFF_MAX)

            base_sleep = CHECK_INTERVAL + random.randint(-JITTER_SECONDS, JITTER_SECONDS)
            sleep_for = max(0, base_sleep + backoff - (time.time() - start))
            logging.info("Sleep %.1fs (backoff %ds).", sleep_for, backoff)
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        logging.info("Interrupted by user.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()