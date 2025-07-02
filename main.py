import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# =======================
# 🔧 НАСТРОЙКИ
# =======================

TOKEN = os.getenv("TOKEN", "5526925742:AAEnEEnlGcnzqcWIVFFeQsniVPDzImuUhvg")
CHAT_IDS = os.getenv("CHAT_IDS", "696601899").split(",")

URL = "https://zakup.sk.kz/#/ext?tabs=advert&q=Экспертиз&adst=PUBLISHED&lst=PUBLISHED&page=1"
CHECK_INTERVAL = 300  # 5 минут

# =======================
# 📩 ОТПРАВКА В TELEGRAM
# =======================

def send_telegram_message(text):
    for chat_id in CHAT_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = {'chat_id': chat_id, 'text': text}
        try:
            requests.post(url, data=data, timeout=10)
        except Exception as e:
            print(f"❌ Ошибка при отправке в Telegram ({chat_id}): {e}")

# =======================
# 📊 ПАРСИНГ ЛОТОВ
# =======================

def get_lot_count(driver):
    print("⏳ Загружаем страницу...")
    driver.get(URL)
    time.sleep(3)

    try:
        print("⏳ Выполняем JavaScript для получения текста 'Найдено ...'")
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div.m-sidebar__layout.ng-star-inserted"))
        )

        # JavaScript для точного получения текста
        text = driver.execute_script("""
            let el = document.querySelector("div.m-sidebar__layout.ng-star-inserted");
            return el ? el.innerText : "";
        """)

        print("📄 JS возвратил текст:")
        print(text)

        digits = [s for s in text.replace('\xa0', ' ').split() if s.isdigit()]
        if not digits:
            print("⚠️ Не удалось найти число в тексте")
            return -1

        number = int(digits[0])
        print(f"✅ Обнаружено количество лотов: {number}")
        return number

    except Exception as e:
        print(f"❌ Ошибка при получении количества лотов: {e}")
        send_telegram_message(f"❌ Ошибка при получении количества лотов: {e}")
        return -1

# =======================
# 🔁 ОСНОВНОЙ ЦИКЛ
# =======================

def main():
    def create_driver():
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-software-rasterizer')
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    driver = create_driver()
    last_count = -1

    while True:
        try:
            count = get_lot_count(driver)
            if count != -1 and count != last_count:
                if last_count != -1:
                    diff = count - last_count
                    sign = "+" if diff > 0 else "-"
                    message = f"🔔 Количество лотов изменилось: {last_count} → {count} ({sign}{abs(diff)})"
                    send_telegram_message(message)
                last_count = count
            else:
                print("ℹ️ Количество лотов не изменилось.")
        except Exception as e:
            print(f"❌ Ошибка в основном цикле: {e}")
            send_telegram_message(f"❌ Ошибка в основном цикле: {e}")
            print("🔁 Перезапуск драйвера...")
            try:
                driver.quit()
            except:
                pass
            driver = create_driver()

        print(f"⏳ Ожидание {CHECK_INTERVAL // 60} минут...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
