"""
Instagram Bot - Utility Functions
Yordamchi funksiyalar
"""

import time
import random
import logging
import requests
from datetime import datetime

import config

logger = logging.getLogger(__name__)


def get_human_delay(min_sec: int, max_sec: int) -> int:
    """Insoniy vaqt oralig'i (Gauss taqsimoti bilan)"""
    mean = (min_sec + max_sec) / 2
    std = (max_sec - min_sec) / 4
    delay = int(random.gauss(mean, std))
    return max(min_sec, min(max_sec, delay))


def update_heartbeat():
    """Bot tirikligini bildirish uchun timestamp yozish"""
    try:
        with open("heartbeat.txt", "w") as f:
            f.write(str(time.time()))
    except:
        pass


def safe_goto(page, url: str, timeout: int = 45000, retries: int = 2) -> bool:
    """Xavfsiz sahifaga o'tish - timeout va retry bilan"""
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return True
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"⚠️ Sahifa yuklanmadi ({attempt+1}/{retries}): {url[:50]}...")
                time.sleep(5)
            else:
                logger.error(f"❌ Sahifa yuklanmadi: {url[:50]}... - {str(e)[:50]}")
                return False
    return False


def send_telegram_msg(text: str):
    """Telegramga xabar yuborish (Requests orqali - Conflict bo'lmaydi)"""
    try:
        if config.ADMIN_IDS:
            admin_id = config.ADMIN_IDS[0]
            token = config.TELEGRAM_BOT_TOKEN
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": admin_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code != 200:
                logger.error(f"❌ Telegram Error {resp.status_code}: {resp.text}")
        else:
            logger.warning("⚠️ ADMIN_IDS topilmadi, xabar yuborilmadi.")
    except Exception as e:
        logger.error(f"❌ Telegram Connection Error: {e}")


def refresh_page_if_stuck(page) -> bool:
    """Sahifani yangilash (qotib qolganda)"""
    try:
        logger.info("🔄 Sahifa yangilanmoqda...")
        page.reload(wait_until="commit", timeout=15000)
        time.sleep(3)
        logger.info("✅ Sahifa yangilandi")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Sahifa yangilashda xato: {e}")
        # Fallback: home sahifaga o'tish
        try:
            page.goto("https://www.instagram.com/", wait_until="commit", timeout=15000)
            time.sleep(3)
        except:
            pass
        return False


def smart_sleep(seconds: int, check_func=None) -> bool:
    """
    Kutish davomida buyruqlarni tekshirish. 
    Agar buyruq o'zgarsa True qaytaradi.
    
    Args:
        seconds: Kutish vaqti (sekund)
        check_func: Har 2 sekundda chaqiriladigan funksiya. True qaytarsa - kutish to'xtaydi.
    """
    import database
    
    slept = 0
    while slept < seconds:
        time.sleep(1)
        slept += 1
        if slept % 2 == 0 and check_func:
            if check_func():
                return True
        elif slept % 2 == 0:
            current = database.get_config("current_cycle")
            if current not in ['cleanup', 'auto']: 
                logger.info(f"⚡ Kutish to'xtatildi! Yangi buyruq: {current}")
                return True
    return False
