"""
Instagram Follow/Unfollow Bot (Browser-based)
Playwright orqali ishlaydi - Instagram xavfsizlik tekshiruvlarini chetlab o'tadi.

Bu bot brauzer orqali ishlaydi, shuning uchun:
1. Oldin brauzerda login qiling
2. Bot o'sha session'dan foydalanadi
"""

import json
import time
import random
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from colorama import init, Fore, Style

# Playwright import
try:
    from playwright.sync_api import sync_playwright, Page
except ImportError:
    pass

import config
import keep_alive
import database
import migrate_json_to_sqlite

# Colorama init
init(autoreset=True)

# Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class InstagramBrowserBot:
    """Instagram bot - brauzer orqali ishlaydi"""
    
    def __init__(self):
        # Baza ishga tushirish
        database.init_db()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def get_human_delay(self, min_sec: int, max_sec: int) -> int:
        """Insoniy vaqt oralig'i"""
        mean = (min_sec + max_sec) / 2
        std = (max_sec - min_sec) / 4
        delay = int(random.gauss(mean, std))
        return max(min_sec, min(max_sec, delay))

    def start_browser(self) -> bool:
        """Brauzerni ishga tushirish"""
        logger.info("🌐 Brauzer ishga tushirilmoqda...")
        
        try:
            self.playwright = sync_playwright().start()
            
            # Persistent context (cookie'lar saqlanadi)
            user_data_dir = Path("browser_data")
            user_data_dir.mkdir(exist_ok=True)
            
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=config.HEADLESS,  # Configdan o'qish
                args=["--no-sandbox", "--disable-setuid-sandbox"] if config.HEADLESS else [],
                viewport={"width": 1280, "height": 800},
                locale="en-US"
            )
            
            # 🍪 Cookie'larni yuklash (Koyeb uchun)
            cookie_file = Path("playwright_cookies.json")
            if cookie_file.exists():
                try:
                    with open(cookie_file, 'r', encoding='utf-8') as f:
                        cookies = json.load(f)
                        self.context.add_cookies(cookies)
                        logger.info(f"🍪 {len(cookies)} ta cookie yuklandi")
                except Exception as e:
                    logger.error(f"❌ Cookie yuklash xatosi: {e}")
            
            self.page = self.context.new_page()
            logger.info("✅ Brauzer tayyor")
            return True
            
        except Exception as e:
            logger.error(f"❌ Brauzer xatosi: {e}")
            return False

    def login(self) -> bool:
        """Instagram'ga kirish"""
        logger.info("🔐 Instagram tekshirilmoqda...")
        
        # Instagram'ga o'tish
        try:
            self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            logger.warning(f"⚠️ Sekin internet: {e}")
            self.page.screenshot(path="error_nav.png")
            
        time.sleep(5)
        
        # Login holatini tekshirish
        if self._is_logged_in():
            logger.info(f"✅ Allaqachon login qilingan!")
            return True
        
        # Login qilish
        logger.info(f"📱 @{config.INSTAGRAM_USERNAME} bilan kirilmoqda...")
        
        try:
            # Username
            username_input = self.page.locator('input[name="username"]')
            username_input.fill(config.INSTAGRAM_USERNAME)
            time.sleep(0.5)
            
            # Password
            password_input = self.page.locator('input[name="password"]')
            password_input.fill(config.INSTAGRAM_PASSWORD)
            time.sleep(0.5)
            
            # Login button
            login_btn = self.page.locator('button[type="submit"]')
            login_btn.click()
            
            # Kutish
            time.sleep(5)
            
            # Tekshirish
            if self._is_logged_in():
                logger.info("✅ Login muvaffaqiyatli!")
                
                # "Save Info" popup yopish
                try:
                    not_now = self.page.locator("text=Not Now").first
                    if not_now.is_visible():
                        not_now.click()
                        time.sleep(1)
                except:
                    pass
                    
                return True
            else:
                # Challenge yoki xato bormi?
                logger.warning("⚠️ Login muvaffaqiyatsiz. Tekshiring...")
                return False
                
        except Exception as e:
            logger.error(f"❌ Login xatosi: {e}")
            return False
    
    def _is_logged_in(self) -> bool:
        """Login holatini tekshirish"""
        try:
            # Profile link bormi?
            profile_link = self.page.locator(f'a[href="/{config.INSTAGRAM_USERNAME}/"]')
            return profile_link.count() > 0
        except:
            return False
    
    def get_followers_of_target(self, count: int = 30) -> list:
        """Target akkauntning followerlarini olish"""
        logger.info(f"🎯 @{config.TARGET_ACCOUNT} followerlarini olmoqda...")
        
        try:
            # Target profilga o'tish
            self.page.goto(f"https://www.instagram.com/{config.TARGET_ACCOUNT}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
            # Followers tugmasini bosish
            followers_link = self.page.locator('a[href$="/followers/"]').first
            followers_link.click()
            time.sleep(5)
            self.page.screenshot(path="debug_followers_dialog.png")
            
            # Deep Scroll Logic
            users = []
            scroll_count = 0
            MAX_SCROLLS = 100 # Chuqur qidirish
            
            logger.info("🔍 Deep Scroll boshlandi: Faqat yangi (bazada yo'q) userlar qidirilmoqda...")
            
            while len(users) < count and scroll_count < MAX_SCROLLS:
                dialog = self.page.locator('div[role="dialog"]').first
                follower_links = dialog.locator('a')
                current_batch_count = follower_links.count()
                
                logger.debug(f"📜 Scroll #{scroll_count}: {current_batch_count} ta link ko'rildi")

                for i in range(current_batch_count):
                    if len(users) >= count:
                        break
                    try:
                        href = follower_links.nth(i).get_attribute("href")
                        if href and href.startswith("/") and len(href) > 2:
                            username = href.strip("/").split("/")[0]
                            
                            # Validatsiya
                            if not username or username == config.TARGET_ACCOUNT:
                                continue
                            
                            # 1. Avval topilganmi?
                            if username in users:
                                continue
                                
                            # 2. Bazada bormi?
                            if database.get_user(username):
                                # logger.debug(f"♻️ Eski user (Bazada bor): {username}")
                                continue
                                
                            # Yangi topildi!
                            users.append(username)
                    except:
                        continue
                
                if len(users) >= count:
                    logger.info(f"✅ Yetarlicha yangi user topildi: {len(users)} ta")
                    break
                
                # Scroll - Mouse Wheel usuli
                try:
                    box = dialog.bounding_box()
                    if box:
                        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        self.page.mouse.wheel(0, 5000)
                        logger.info(f"🖱️ Scroll qilinmoqda... ({len(users)}/{count} topildi)")
                    else:
                        dialog.evaluate("el => el.scrollTop += 1500")
                        
                    time.sleep(3) # Loading...
                except Exception as e:
                    logger.warning(f"⚠️ Scroll xatosi: {e}")
                
                scroll_count += 1
            
            # Dialogni yopish
            self.page.keyboard.press("Escape")
            time.sleep(1)
            
            logger.info(f"✅ {len(users)} ta follower topildi")
            return users[:count]
            
        except Exception as e:
            logger.error(f"❌ Followers olishda xato: {e}")
            return []
    
    def follow_user(self, username: str) -> bool:
        """Foydalanuvchini follow qilish"""
        
        # Limit tekshirish
        daily_follow, _ = database.get_today_stats()
        if daily_follow >= config.DAILY_FOLLOW_LIMIT:
            logger.warning(f"⚠️ Kunlik limit tugadi ({daily_follow})")
            return False
        
        # Bazada bormi?
        user = database.get_user(username)
        if user:
            logger.info(f"⏭️ @{username} allaqachon bazada (Status: {user['status']})")
            return False
        
        try:
            # Profilga o'tish
            self.page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
            
            # Follow tugmasini topish
            follow_btn = self.page.locator('button:has-text("Follow")').first
            
            if not follow_btn.is_visible():
                logger.info(f"⏭️ @{username} allaqachon follow qilingan yoki mavjud emas")
                database.add_user(username) # Bazaga qo'shib qo'yamiz
                return False
            
            # Follow bosish
            follow_btn.click()
            time.sleep(2)

            # "Pending" popup tekshiruvi
            try:
                pending_dialog = self.page.locator('div[role="dialog"]:has-text("pending")')
                if pending_dialog.is_visible():
                    logger.info("ℹ️ 'Request Pending' oynasi chiqdi. 'OK' bosilmoqda...")
                    ok_btn = pending_dialog.locator('button:has-text("OK")')
                    if ok_btn.is_visible():
                        ok_btn.click()
                        time.sleep(1)
            except Exception as e:
                pass
            
            # Bazaga yozish (SQLite)
            if database.add_user(username):
                daily_follow, _ = database.get_today_stats()
                logger.info(f"{Fore.GREEN}✅ Follow: @{username} [{daily_follow}/{config.DAILY_FOLLOW_LIMIT}]")
                return True
            else:
                return False
            
        except Exception as e:
            logger.error(f"❌ Follow xatosi @{username}: {e}")
            return False
    
    def get_my_followers(self) -> set:
        """O'z followerlarimizni olish"""
        logger.info("📊 O'z followerlarimiz tekshirilmoqda...")
        try:
            # O'z profilga o'tish
            self.page.goto(f"https://www.instagram.com/{config.INSTAGRAM_USERNAME}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
            # Followers tugmasini bosish
            followers_link = self.page.locator('a[href$="/followers/"]').first
            followers_link.click()
            time.sleep(3)
            
            followers = set()
            scroll_count = 0
            prev_count = 0
            
            while scroll_count < 20:  # Max 20 scroll
                follower_links = self.page.locator('div[role="dialog"] a[href^="/"]')
                
                for i in range(follower_links.count()):
                    try:
                        href = follower_links.nth(i).get_attribute("href")
                        if href and href.startswith("/"):
                            username = href.strip("/").split("/")[0]
                            if username:
                                followers.add(username)
                    except:
                        continue
                
                # Scroll
                try:
                     dialog = self.page.locator('div[role="dialog"]').first
                     self.page.mouse.wheel(0, 3000)
                     time.sleep(1)
                except:
                    pass
                
                scroll_count += 1
                if len(followers) == prev_count:
                    break
                prev_count = len(followers)
            
            self.page.keyboard.press("Escape")
            time.sleep(1)
            
            logger.info(f"✅ {len(followers)} ta follower topildi")
            return followers
            
        except Exception as e:
            logger.error(f"❌ Followers olishda xato: {e}")
            return set()
    
    def check_and_unfollow(self):
        """24 soat o'tganlarni tekshirish va unfollow qilish"""
        logger.info("🔍 24 soat tekshiruvi boshlanmoqda...")
        
        waiting_users = database.get_waiting_users()
        if not waiting_users:
            logger.info("✅ Tekshiradiganlar yo'q")
            return

        my_followers = self.get_my_followers()
        now = datetime.now()
        to_unfollow = []
        
        for user in waiting_users:
            followed_at = datetime.fromisoformat(user['followed_at'])
            hours = (now - followed_at).total_seconds() / 3600
            
            if hours >= 24:
                username = user['username']
                
                if username in my_followers:
                    logger.info(f"{Fore.GREEN}✅ @{username} follow qaytardi!")
                    database.update_status(username, 'followed_back')
                else:
                    to_unfollow.append(username)
                    logger.info(f"{Fore.YELLOW}❌ @{username} follow qaytarmagan ({hours:.1f} soat)")
        
        # Unfollow
        for username in to_unfollow:
            if self.unfollow_user(username):
                delay = self.get_human_delay(config.UNFOLLOW_DELAY_MIN, config.UNFOLLOW_DELAY_MAX)
                logger.info(f"⏳ {delay} sekund kutilmoqda...")
                time.sleep(delay)
    
    def unfollow_user(self, username: str) -> bool:
        """Foydalanuvchini unfollow qilish"""
        
        _, daily_unfollow = database.get_today_stats()
        if daily_unfollow >= config.DAILY_UNFOLLOW_LIMIT:
            logger.warning(f"⚠️ Kunlik unfollow limiti tugadi")
            return False
        
        try:
            # Profilga o'tish
            self.page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
            
            # Following tugmasini topish (following bo'lsa)
            following_btn = self.page.locator('button:has-text("Following")').first
            
            if not following_btn.is_visible():
                logger.info(f"⏭️ @{username} allaqachon unfollow qilingan")
                database.update_status(username, 'unfollowed') # Bazani to'g'irlash
                return False
            
            # Following tugmasini bosish
            following_btn.click()
            time.sleep(1)
            
            # Unfollow tugmasini bosish
            unfollow_btn = self.page.locator('button:has-text("Unfollow")').first
            unfollow_btn.click()
            time.sleep(2)
            
            # Bazani yangilash
            database.update_status(username, 'unfollowed')
            
            _, daily_unfollow = database.get_today_stats()
            logger.info(f"{Fore.RED}🚫 Unfollow: @{username} [{daily_unfollow}/{config.DAILY_UNFOLLOW_LIMIT}]")
            return True
            
        except Exception as e:
            logger.error(f"❌ Unfollow xatosi @{username}: {e}")
            return False
    
    def run_follow_cycle(self, count: int = 20):
        """Follow sikli"""
        logger.info(f"\n{'='*50}")
        logger.info("🚀 FOLLOW SIKLI BOSHLANDI")
        logger.info(f"{'='*50}\n")
        
        users = self.get_followers_of_target(count)
        
        if not users:
            logger.warning("⚠️ Foydalanuvchi topilmadi")
            return
        
        followed = 0
        for username in users:
            if self.follow_user(username):
                followed += 1
                delay = self.get_human_delay(config.FOLLOW_DELAY_MIN, config.FOLLOW_DELAY_MAX)
                logger.info(f"⏳ {delay} sekund ({delay/60:.1f} daqiqa) kutilmoqda...")
                time.sleep(delay)
        
        logger.info(f"\n✅ Follow sikli tugadi: {followed} ta follow qilindi\n")
    
    def show_stats(self):
        """Statistika"""
        total, waiting, backed = database.get_total_stats()
        d_follow, d_unfollow = database.get_today_stats()
        
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.YELLOW}📊 STATISTIKA (SQLite)")
        print(f"{Fore.CYAN}{'='*50}")
        print(f"{Fore.WHITE}📝 Jami bazada: {Fore.GREEN}{total}")
        print(f"{Fore.WHITE}⏳ Kutilmoqda: {Fore.YELLOW}{waiting}")
        print(f"{Fore.WHITE}✅ Qaytardi: {Fore.GREEN}{backed}")
        print(f"{Fore.CYAN}{'='*50}")
        print(f"{Fore.WHITE}📅 Bugun follow: {d_follow}/{config.DAILY_FOLLOW_LIMIT}")
        print(f"{Fore.WHITE}📅 Bugun unfollow: {d_unfollow}/{config.DAILY_UNFOLLOW_LIMIT}")
        print(f"{Fore.CYAN}{'='*50}\n")
    
    def close(self):
        """Brauzerni yopish"""
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()


def main():
    """Asosiy funksiya"""
    # Web serverni ishga tushirish (Koyeb uchun)
    try:
        keep_alive.keep_alive()
    except Exception as e:
        logger.error(f"Keep-alive start error: {e}")

    # Migratsiya
    try:
        migrate_json_to_sqlite.migrate()
    except Exception as e:
        logger.error(f"Migration error: {e}")

    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗
{Fore.CYAN}║{Fore.YELLOW}     📸 INSTAGRAM BOT (BROWSER + SQLITE)                      {Fore.CYAN}║
{Fore.CYAN}║{Fore.WHITE}     24/7 Avtomatik rejim (Uyqusiz!)                           {Fore.CYAN}║
{Fore.CYAN}╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
    """)
    
    bot = InstagramBrowserBot()
    
    if not bot.start_browser():
        return
    
    if not bot.login():
        print(f"{Fore.YELLOW}⚠️ Login muvaffaqiyatsiz.")
        if config.HEADLESS:
             logger.error("❌ Headless rejimda login qilib bo'lmadi. Dastur to'xtatildi.")
             bot.close()
             return
        
        print(f"{Fore.WHITE}   Brauzerda qo'lda login qiling va qayta urinib ko'ring.")
        # Serverda input() ishlatilmaydi
        if not config.HEADLESS:
            try:
                input("Login qilganingizdan keyin ENTER bosing...")
            except:
                pass
            
        if not bot._is_logged_in():
            print(f"{Fore.RED}❌ Hali ham login bo'lmagan. Dastur tugatildi.")
            bot.close()
            return
    
    # 🤖 Serverda avtomatik ishga tushish (Menyusiz)
    if config.HEADLESS:
        logger.info("🤖 Server rejimi aniqlandi: 24/7 Avtomatik rejim ishga tushmoqda...")
        print(f"\n{Fore.YELLOW}🤖 AVTOMATIK REJIM (24/7) - Server")
        
        try:
            while True:
                # Tungi rejim OLIB TASHLANDI
                # Bot endi 24/7 ishlaydi, faqat oraliq vaqtlar (delay) bilan.
                
                # 1. Follow sikli
                bot.run_follow_cycle(20)
                bot.show_stats()
                
                # 2. Unfollow sikli
                bot.check_and_unfollow()
                bot.show_stats()
                
                # 3. Kutish (Random 1-2 soat)
                # Odamga o'xshash uchun qat'iy 1 soat emas, random qilamiz
                wait_time = random.randint(3600, 7200) 
                logger.info(f"⏳ Sikl tugadi. {wait_time/60:.1f} daqiqa kutilmoqda dam olish uchun...")
                time.sleep(wait_time)
                
        except KeyboardInterrupt:
            logger.info("⚠️ To'xtatildi")
        finally:
            bot.close()
        return

    # 🖥️ Lokal kompyuterda menyu chiqarish
    try:
        while True:
            print(f"""
{Fore.CYAN}┌───────────────────────────────────────┐
{Fore.CYAN}│{Fore.YELLOW} 🎮 MENYU (SQLite)                     {Fore.CYAN}│
{Fore.CYAN}├───────────────────────────────────────┤
{Fore.CYAN}│{Fore.WHITE} 1. 🚀 Follow siklini boshlash         {Fore.CYAN}│
{Fore.CYAN}│{Fore.WHITE} 2. 🔍 24 soat tekshirish + unfollow   {Fore.CYAN}│
{Fore.CYAN}│{Fore.WHITE} 3. 🤖 Avtomatik rejim (24/7)          {Fore.CYAN}│
{Fore.CYAN}│{Fore.WHITE} 4. 📊 Statistika                      {Fore.CYAN}│
{Fore.CYAN}│{Fore.WHITE} 5. 🚪 Chiqish                         {Fore.CYAN}│
{Fore.CYAN}└───────────────────────────────────────┘
            """)
            
            choice = input(f"{Fore.CYAN}Tanlang (1-5): {Style.RESET_ALL}").strip()
            
            if choice == "1":
                count = input(f"Nechta follow? (default: 20): ").strip()
                count = int(count) if count.isdigit() else 20
                bot.run_follow_cycle(count)
                
            elif choice == "2":
                bot.check_and_unfollow()
                
            elif choice == "3":
                print(f"\n{Fore.YELLOW}🤖 AVTOMATIK REJIM")
                print(f"{Fore.RED}To'xtatish: Ctrl+C\n")
                
                while True:
                    # Tungi rejim yo'q
                    bot.run_follow_cycle(20)
                    bot.show_stats()
                    bot.check_and_unfollow()
                    bot.show_stats()
                    
                    wait_time = random.randint(3600, 7200) 
                    logger.info(f"⏳ {wait_time/60:.1f} daqiqa kutilmoqda...")
                    time.sleep(wait_time)
                    
            elif choice == "4":
                bot.show_stats()
                
            elif choice == "5":
                break
                
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠️ To'xtatildi")
        
    finally:
        bot.close()
        print(f"{Fore.GREEN}👋 Xayr!")


if __name__ == "__main__":
    main()
