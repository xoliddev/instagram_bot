"""
Browser to Instagrapi Session Converter
Playwright brauzeridagi sessionni instagrapi formatiga o'tkazadi
"""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from instagrapi import Client
import config

def convert_session():
    print("🔄 Session ko'chirilmoqda...")
    
    with sync_playwright() as p:
        # Browser ma'lumotlari papkasi (o'sha papka bo'lishi kerak)
        user_data_dir = Path("browser_data")
        
        if not user_data_dir.exists():
            print("❌ Brauzer ma'lumotlari topilmadi. Avval bot_browser.py ni ishlatib login qiling!")
            return
            
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True # Orqa fonda ishlash
        )
        
        page = browser.pages[0]
        page.goto("https://www.instagram.com/")
        
        # Cookie'larni olish
        cookies = browser.cookies()
        
        # Instagrapi uchun formatlash
        instagrapi_cookies = {}
        for cookie in cookies:
            instagrapi_cookies[cookie['name']] = cookie['value']
            
        browser.close()
        
        if 'sessionid' not in instagrapi_cookies:
            print("❌ Session topilmadi! Brauzerda login qilmagansiz.")
            return

        # Instagrapi client yaratish
        cl = Client()
        
        # Cookie'larni yuklash
        cl.set_settings({'cookies': instagrapi_cookies})
        
        # Sessionni test qilish
        try:
            cl.get_timeline_feed()
            print("✅ Session ishlayapti!")
            
            # Faylga saqlash
            cl.dump_settings(Path(config.SESSION_FILE))
            print(f"✅ Session saqlandi: {config.SESSION_FILE}")
            print("\nEndi serverga joylash uchun:")
            print(f"1. {config.SESSION_FILE}")
            print(f"2. config.py")
            print(f"3. bot.py")
            print("fayllarini yuklasangiz bo'ldi.")
            
        except Exception as e:
            print(f"❌ Session bilan muammo: {e}")

if __name__ == "__main__":
    convert_session()
