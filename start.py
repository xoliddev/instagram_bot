#!/usr/bin/env python3
"""
Startup script - Both bots run together
Instagram Bot + Telegram Bot + Auto Backup
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

def auto_restore_database():
    """Startup da bazani Gist dan qayta yuklash"""
    try:
        import backup
        backup.auto_restore_if_empty()
    except Exception as e:
        logger.error(f"❌ Auto-restore xatosi: {e}")

def periodic_backup():
    """Har soatda avtomatik backup"""
    while True:
        time.sleep(3600)  # 1 soat kutish
        try:
            import backup
            backup.backup_to_gist()
            logger.info("💾 Avtomatik backup muvaffaqiyatli")
        except Exception as e:
            logger.error(f"❌ Periodic backup xatosi: {e}")

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
    
    # 1. Bazani restore qilish (agar kerak bo'lsa)
    logger.info("📥 Baza tekshirilmoqda...")
    auto_restore_database()
    
    # 2. Periodic backup thread
    backup_thread = threading.Thread(target=periodic_backup, daemon=True)
    backup_thread.start()
    logger.info("💾 Avtomatik backup har 1 soatda ishlaydi")
    
    # 3. Instagram bot - alohida thread (Auto-Restart bilan)
    def start_insta_thread():
        thread = threading.Thread(target=run_instagram_bot, daemon=True)
        thread.start()
        return thread

    insta_thread = start_insta_thread()
    
    # Monitor thread
    def monitor_threads():
        nonlocal insta_thread
        while True:
            time.sleep(10)
            if not insta_thread.is_alive():
                logger.warning("⚠️ Instagram Bot Thread to'xtab qoldi! Qayta ishga tushirilmoqda...")
                insta_thread = start_insta_thread()
    
    monitor = threading.Thread(target=monitor_threads, daemon=True)
    monitor.start()
    
    # 4. Telegram bot - main thread
    time.sleep(3)
    run_telegram_bot()

if __name__ == "__main__":
    main()

