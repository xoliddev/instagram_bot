#!/usr/bin/env python3
"""
Startup script - Both bots run together
Instagram Bot + Telegram Bot
"""
import threading
import time
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_instagram_bot():
    """Instagram botni ishga tushirish"""
    try:
        logger.info("🤖 Instagram Bot ishga tushmoqda...")
        import bot_browser
        bot_browser.main()
    except Exception as e:
        logger.error(f"❌ Instagram Bot xatosi: {e}")

def run_telegram_bot():
    """Telegram botni ishga tushirish"""
    try:
        logger.info("📱 Telegram Bot ishga tushmoqda...")
        import telegram_bot
        telegram_bot.run_telegram_bot()
    except Exception as e:
        logger.error(f"❌ Telegram Bot xatosi: {e}")

def main():
    """Ikkala botni parallel ishga tushirish"""
    logger.info("🚀 Barcha botlar ishga tushmoqda...")
    
    # Instagram bot - alohida thread
    instagram_thread = threading.Thread(target=run_instagram_bot, daemon=True)
    instagram_thread.start()
    
    # Telegram bot - main thread (async loop needs main)
    # Bir oz kutamiz Instagram bot boshlangunga qadar
    time.sleep(3)
    
    # Telegram bot
    run_telegram_bot()

if __name__ == "__main__":
    main()
