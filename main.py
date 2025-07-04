"""
Мониторинг лотов zakup.sk.kz → Telegram.

• Каждые 5 минут опрашивает страницу.
• Если сайт/драйвер отпадает, код:
    – ловит исключение;
    – делает паузу (back-off);
    – при накоплении N ошибок перезапускает Chrome-драйвер;
    – присылает уведомление в TG только о первом сбое и о «выздоровлении».
"""

from future import annotations

import random
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

# ─────────────────────────────────────
# 🔧 НАСТРОЙКИ
# ─────────────────────────────────────
TOKEN: str = "5526925742:AAEnEEnlGcnzqcWIVFFeQsniVPDzImuUhvg"
CHAT_IDS: list[str] = ["696601899"]

URL = (
    "https://zakup.sk.kz/#/ext?"
    "tabs=advert&q=Экспертиз&adst=PUBLISHED&lst=PUBLISHED&page=1"
)
WAIT_SELECTOR = "div.block-footer"   # блок, где есть «Найдено …»

CHECK_INTERVAL = 300                 # базовый интервал (5 мин)
JITTER_SECONDS = 30                  # ± джиттер, чтобы не бить в ровную минуту
MAX_CONSECUTIVE_ERRORS = 4           # сколько подряд ошибок → рестарт драйвера
DRIVER_REFRESH_HOURS = 6             # профилактический рестарт каждые N часов

BACKOFF_STEP = 60                    # секунд добавить к задержке после ошибки
BACKOFF_MAX = 15 * 60                # не больше 15 мин между попытками при падениях

LOG_FILE = "monitor.log"
# ─────────────────────────────────────

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
        except Exception as exc:      # pylint: disable=broad-except
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
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

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
    time.sleep(2)           # даём JS дорисоваться
    txt = driver.execute_script("return document.body.innerText")
    return parse_count(txt)

# ─────────────────────────────────────
# 🔁 ОСНОВНОЙ ЦИКЛ
# ─────────────────────────────────────
def main() -> None:
    driver = make_driver()
    driver_birth = datetime.now(tz=timezone.utc)

    last_count: int | None = None
    consecutive_err = 0
    backoff = 0
    sent_down_notice = False

    tg_send("✅ Монитор запущен.")
    logging.info("Started monitor.")

    try:
        while True:
            start = time.time()

            # профилактический рестарт драйвера раз в N часов
            if datetime.now(tz=timezone.utc) - driver_birth > timedelta(hours=DRIVER_REFRESH_HOURS):
                logging.info("Refreshing Chrome driver (%.1fh).", DRIVER_REFRESH_HOURS)
                try:
                    driver.quit()
                except Exception:      # pylint: disable=broad-except
                    pass
                driver = make_driver()
                driver_birth = datetime.now(tz=timezone.utc)

            try:
                count = fetch_count(driver)
                if count is None:
                    raise ValueError("Не найдено число лотов.")

                # если были ошибки ранее — сайт «ожил»
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
                logging.debug("Trace:\n%s", traceback.format_exc())

                # первая ошибка → сообщение
                if not sent_down_notice:
                    tg_send(f"⚠️ Проблема с zakup.sk.kz: {exc}")
                    sent_down_notice = True

                # если ошибок подряд много — полный рестарт драйвера
                if consecutive_err >= MAX_CONSECUTIVE_ERRORS:
                    logging.error("Too many errors, restarting driver.")
                    try:
                        driver.quit()
                    except Exception:  # pylint: disable=broad-except
                        pass
                    driver = make_driver()
                    driver_birth = datetime.now(tz=timezone.utc)
                    consecutive_err = 0

                # увеличиваем паузу
                backoff = min(backoff + BACKOFF_STEP, BACKOFF_MAX)

            # вычисляем, сколько спать
            base_sleep = CHECK_INTERVAL + random.randint(-JITTER_SECONDS, JITTER_SECONDS)
            sleep_for = max(0, base_sleep + backoff - (time.time() - start))
            logging.info("Sleep %.1fs (backoff %ds).", sleep_for, backoff)
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        logging.info("Interrupted by user.")
    finally:
        try:
            driver.quit()
        except Exception:              # pylint: disable=broad-except
            pass
            

if __name__ == "__main__":
    main()