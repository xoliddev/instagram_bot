
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

def export_cookies():
    print("🔄 Cookie'lar eksport qilinmoqda...")
    
    with sync_playwright() as p:
        user_data_dir = Path("browser_data")
        
        if not user_data_dir.exists():
            print("❌ Brauzer ma'lumotlari topilmadi.")
            return

        print(f"📂 {user_data_dir} dan o'qilmoqda...")
        
        # Brauzerni ochish (headless)
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True
        )
        
        # Instagramga kirib cookie'larni yangilash
        page = context.new_page()
        try:
            page.goto("https://www.instagram.com/", timeout=30000)
            page.wait_for_load_state("networkidle")
        except:
            pass

        cookies = context.cookies()
        context.close()
        
        if not cookies:
            print("❌ Cookie'lar bo'sh!")
            return

        with open("playwright_cookies.json", "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
            
        print(f"✅ {len(cookies)} ta cookie saqlandi: playwright_cookies.json")

if __name__ == "__main__":
    export_cookies()
