import logging, random, re, time, traceback, requests
from datetime import datetime, timedelta, timezone

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# ───── НАСТРОЙКИ ─────
TOKEN     = "5526925742:AAEnEEnlGcnzqcWIVFFeQsniVPDzImuUhvg"
CHAT_IDS  = ["696601899"]

URL       = ("https://zakup.sk.kz/#/ext?"
             "tabs=advert&q=Экспертиз&adst=PUBLISHED&lst=PUBLISHED&page=1")
WAIT_SEL  = "div.block-footer"

CHECK_INTERVAL       = 300      # 5 мин
JITTER_SECONDS       = 30
MAX_CONSEC_ERRORS    = 4
DRIVER_REFRESH_HOURS = 6
BACKOFF_STEP         = 60
BACKOFF_MAX          = 900

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")

# ─── Telegram ───
def tg_send(msg: str):
    for cid in CHAT_IDS:
        try:
            r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                              data={"chat_id": cid, "text": msg}, timeout=10)
            if r.status_code != 200:
                logging.error("TG %s: %s", r.status_code, r.text)
        except Exception as e:
            logging.error("TG error: %s", e)

# ─── WebDriver ───
def make_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service("/usr/bin/chromedriver"),
                            options=opts)

# ─── Парсинг ───
_rx = re.compile(r"Найдено\s+(\d+)")
def fetch_count(driver):
    driver.get(URL)
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, WAIT_SEL)))
    txt = driver.execute_script("return document.body.innerText")
    m = _rx.search(txt)
    return int(m.group(1)) if m else None

# ─── Цикл мониторинга ───
def main():
    driver = make_driver()
    born   = datetime.now(tz=timezone.utc)

    last, err, backoff, down = None, 0, 0, False
    tg_send("✅ Монитор запущен")

    while True:
        start = time.time()

        # профилактика
        if datetime.now(tz=timezone.utc) - born > timedelta(hours=DRIVER_REFRESH_HOURS):
            logging.info("Refresh driver (%.1fh)", DRIVER_REFRESH_HOURS)
            driver.quit(); driver = make_driver(); born = datetime.now(tz=timezone.utc)

        try:
            cnt = fetch_count(driver)
            if cnt is None:
                raise ValueError("Строка «Найдено …» не найдена")

            if down:
                tg_send("✅ Связь восстановлена"); down = False
            err = backoff = 0

            if last is None:
                last = cnt; logging.info("Initial count: %d", cnt)
            elif cnt != last:
                diff = cnt - last
                arrow = "🔺" if diff > 0 else "🔻"
                msg = f"{arrow} Лоты: {last} → {cnt} (Δ {diff:+})"
                tg_send(msg); logging.info(msg); last = cnt
            else:
                logging.info("Без изменений (%d)", cnt)

        except (TimeoutException, WebDriverException, Exception) as e:
            err += 1
            logging.warning("Fetch failed (%d): %s", err, e)
            logging.debug("Trace:\n%s", traceback.format_exc())

            if not down:
                tg_send(f"⚠️ Проблема с сайтом: {e}"); down = True
            if err >= MAX_CONSEC_ERRORS:
                logging.error("Слишком много ошибок — перезапуск драйвера")
                driver.quit(); driver = make_driver(); born = datetime.now(tz=timezone.utc); err = 0
            backoff = min(backoff + BACKOFF_STEP, BACKOFF_MAX)

        sleep_s = max(0, CHECK_INTERVAL + random.randint(-JITTER_SECONDS, JITTER_SECONDS)
                         + backoff - (time.time() - start))
        logging.info("Sleep %.1fs (backoff %ds)", sleep_s, backoff)
        time.sleep(sleep_s)

if __name__ == "__main__":
    main()