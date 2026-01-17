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
        self.following_data = self._load_following_data()
        self.daily_follow_count = 0
        self.daily_unfollow_count = 0
        self.last_reset_date = datetime.now().date()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
    def _load_following_data(self) -> dict:
        """Bazadan yuklab olish"""
        if Path(config.FOLLOWING_DB).exists():
            try:
                with open(config.FOLLOWING_DB, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Daily statistikalarni tiklash
                    if "daily" in data:
                         try:
                             saved_date = datetime.fromisoformat(data["daily"]["date"]).date()
                             if saved_date == datetime.now().date():
                                 self.daily_follow_count = data["daily"]["follow_count"]
                                 self.daily_unfollow_count = data["daily"]["unfollow_count"]
                                 self.last_reset_date = saved_date
                                 logger.info(f"📅 Bugungi statistika tiklandi: {self.daily_follow_count} follow, {self.daily_unfollow_count} unfollow")
                         except Exception as e:
                             logger.warning(f"⚠️ Daily stats error: {e}")
                    
                    # Compatibility (eski format uchun)
                    if "following" not in data:
                        return {"following": data, "stats": {"total_followed": 0, "total_unfollowed": 0, "followed_back": 0}}
                        
                    logger.info(f"📂 Bazadan {len(data.get('following', {}))} ta yozuv yuklandi")
                    return data
            except Exception as e:
                logger.error(f"❌ Baza yuklash xatosi: {e}")
                pass
        return {"following": {}, "stats": {"total_followed": 0, "total_unfollowed": 0, "followed_back": 0}}
    
    def _save_following_data(self):
        """Bazaga saqlash"""
        data_to_save = {
            "following": self.following_data.get("following", {}),
            "stats": self.following_data.get("stats", {"total_followed": 0, "total_unfollowed": 0, "followed_back": 0}),
            "daily": {
                "date": self.last_reset_date.isoformat(),
                "follow_count": self.daily_follow_count,
                "unfollow_count": self.daily_unfollow_count
            }
        }
        with open(config.FOLLOWING_DB, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
    
    def _reset_daily_counters(self):
        """Kunlik hisoblagichlarni qayta o'rnatish"""
        today = datetime.now().date()
        if today > self.last_reset_date:
            self.daily_follow_count = 0
            self.daily_unfollow_count = 0
            self.last_reset_date = today
            logger.info(f"{Fore.CYAN}📊 Yangi kun! Hisoblagichlar qayta o'rnatildi")
    
    def is_night_time(self) -> bool:
        """Tungi vaqtmi?"""
        hour = datetime.now().hour
        if config.NIGHT_REST_START < config.NIGHT_REST_END:
            return config.NIGHT_REST_START <= hour < config.NIGHT_REST_END
        else:
            return config.NIGHT_REST_START <= hour or hour < config.NIGHT_REST_END
    
    def wait_until_morning(self):
        """Tongga qadar kutish"""
        now = datetime.now()
        if now.hour >= config.NIGHT_REST_START:
            wake = (now + timedelta(days=1)).replace(hour=config.NIGHT_REST_END, minute=0, second=0)
        else:
            wake = now.replace(hour=config.NIGHT_REST_END, minute=0, second=0)
        
        wait_sec = (wake - now).total_seconds()
        logger.info(f"🌙 Tungi dam olish. Uyg'onish: {wake.strftime('%H:%M')} ({wait_sec/3600:.1f} soat)")
        time.sleep(wait_sec)
    
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
            
            users = []
            scroll_count = 0
            max_scrolls = count // 10 + 2
            
            while len(users) < count and scroll_count < max_scrolls:
                # Follower linkalarini olish
                dialog = self.page.locator('div[role="dialog"]').first
                follower_links = dialog.locator('a')
                logger.info(f"DEBUG: Linklar soni: {follower_links.count()}")
                
                for i in range(follower_links.count()):
                    try:
                        href = follower_links.nth(i).get_attribute("href")
                        if href and href.startswith("/") and "/" in href[1:]:
                            username = href.strip("/").split("/")[0]
                            if username and username not in users and username != config.TARGET_ACCOUNT:
                                users.append(username)
                    except:
                        continue
                
                # Scroll - keyboard usuli
                try:
                    # Dialogga focus berib PageDown bosish
                    dialog.click()
                    self.page.keyboard.press("PageDown")
                    time.sleep(1)
                    self.page.keyboard.press("PageDown")
                except:
                    dialog.evaluate("el => el.scrollTop += 500")
                
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
        self._reset_daily_counters()
        
        if self.is_night_time():
            self.wait_until_morning()
        
        if self.daily_follow_count >= config.DAILY_FOLLOW_LIMIT:
            logger.warning(f"⚠️ Kunlik limit tugadi")
            return False
        
        # Bazada bormi?
        if username in [d["username"] for d in self.following_data["following"].values()]:
            logger.info(f"⏭️ @{username} allaqachon bazada")
            return False
        
        try:
            # Profilga o'tish
            self.page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
            
            # Follow tugmasini topish
            follow_btn = self.page.locator('button:has-text("Follow")').first
            
            if not follow_btn.is_visible():
                logger.info(f"⏭️ @{username} allaqachon follow qilingan yoki mavjud emas")
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
            
            # Bazaga yozish
            user_id = username  # Brauzer versiyada username ni ID sifatida ishlatamiz
            self.following_data["following"][user_id] = {
                "username": username,
                "followed_at": datetime.now().isoformat(),
                "status": "waiting",
                "checked": False
            }
            self.following_data["stats"]["total_followed"] += 1
            self._save_following_data()
            
            self.daily_follow_count += 1
            logger.info(f"{Fore.GREEN}✅ Follow: @{username} [{self.daily_follow_count}/{config.DAILY_FOLLOW_LIMIT}]")
            return True
            
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
                
                # Scroll - keyboard usuli
                try:
                    dialog.click()
                    self.page.keyboard.press("PageDown")
                    time.sleep(1)
                    self.page.keyboard.press("PageDown")
                except:
                    dialog.evaluate("el => el.scrollTop += 500")
                
                scroll_count += 1
                
                # Yangi follower qo'shilmadimi?
                if len(followers) == prev_count:
                    break
                prev_count = len(followers)
            
            # Dialogni yopish
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
        
        my_followers = self.get_my_followers()
        now = datetime.now()
        to_unfollow = []
        
        for user_id, data in list(self.following_data["following"].items()):
            if data.get("status") != "waiting":
                continue
            
            followed_at = datetime.fromisoformat(data["followed_at"])
            hours = (now - followed_at).total_seconds() / 3600
            
            if hours >= 24:
                username = data["username"]
                
                if username in my_followers:
                    logger.info(f"{Fore.GREEN}✅ @{username} follow qaytardi!")
                    self.following_data["following"][user_id]["status"] = "followed_back"
                    self.following_data["stats"]["followed_back"] += 1
                else:
                    to_unfollow.append(username)
                    logger.info(f"{Fore.YELLOW}❌ @{username} follow qaytarmagan ({hours:.1f} soat)")
        
        self._save_following_data()
        
        # Unfollow
        for username in to_unfollow:
            if self.unfollow_user(username):
                delay = self.get_human_delay(config.UNFOLLOW_DELAY_MIN, config.UNFOLLOW_DELAY_MAX)
                logger.info(f"⏳ {delay} sekund kutilmoqda...")
                time.sleep(delay)
    
    def unfollow_user(self, username: str) -> bool:
        """Foydalanuvchini unfollow qilish"""
        self._reset_daily_counters()
        
        if self.is_night_time():
            self.wait_until_morning()
        
        if self.daily_unfollow_count >= config.DAILY_UNFOLLOW_LIMIT:
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
                return False
            
            # Following tugmasini bosish
            following_btn.click()
            time.sleep(1)
            
            # Unfollow tugmasini bosish
            unfollow_btn = self.page.locator('button:has-text("Unfollow")').first
            unfollow_btn.click()
            time.sleep(2)
            
            # Bazani yangilash
            for user_id, data in self.following_data["following"].items():
                if data["username"] == username:
                    self.following_data["following"][user_id]["status"] = "unfollowed"
                    self.following_data["following"][user_id]["unfollowed_at"] = datetime.now().isoformat()
                    break
            
            self.following_data["stats"]["total_unfollowed"] += 1
            self._save_following_data()
            
            self.daily_unfollow_count += 1
            logger.info(f"{Fore.RED}🚫 Unfollow: @{username} [{self.daily_unfollow_count}/{config.DAILY_UNFOLLOW_LIMIT}]")
            return True
            
        except Exception as e:
            logger.error(f"❌ Unfollow xatosi @{username}: {e}")
            return False
    
    def run_follow_cycle(self, count: int = 20):
        """Follow sikli"""
        logger.info(f"\n{'='*50}")
        logger.info("🚀 FOLLOW SIKLI BOSHLANDI")
        logger.info(f"{'='*50}\n")
        
        if self.is_night_time():
            self.wait_until_morning()
        
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
        total = len(self.following_data["following"])
        waiting = sum(1 for d in self.following_data["following"].values() if d.get("status") == "waiting")
        backed = sum(1 for d in self.following_data["following"].values() if d.get("status") == "followed_back")
        unfollowed = sum(1 for d in self.following_data["following"].values() if d.get("status") == "unfollowed")
        
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.YELLOW}📊 STATISTIKA")
        print(f"{Fore.CYAN}{'='*50}")
        print(f"{Fore.WHITE}📝 Jami: {Fore.GREEN}{total}")
        print(f"{Fore.WHITE}⏳ Kutilmoqda: {Fore.YELLOW}{waiting}")
        print(f"{Fore.WHITE}✅ Qaytardi: {Fore.GREEN}{backed}")
        print(f"{Fore.WHITE}🚫 Unfollow: {Fore.RED}{unfollowed}")
        print(f"{Fore.CYAN}{'='*50}")
        print(f"{Fore.WHITE}📅 Bugun follow: {self.daily_follow_count}/{config.DAILY_FOLLOW_LIMIT}")
        print(f"{Fore.WHITE}📅 Bugun unfollow: {self.daily_unfollow_count}/{config.DAILY_UNFOLLOW_LIMIT}")
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

    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗
{Fore.CYAN}║{Fore.YELLOW}     📸 INSTAGRAM BOT (BROWSER VERSION)                       {Fore.CYAN}║
{Fore.CYAN}║{Fore.WHITE}     Brauzer orqali ishlaydi - xavfsiz!                        {Fore.CYAN}║
{Fore.CYAN}║{Fore.WHITE}     🌙 Tungi dam olish: 00:00 - 07:00                          {Fore.CYAN}║
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
    
    try:
        while True:
            print(f"""
{Fore.CYAN}┌───────────────────────────────────────┐
{Fore.CYAN}│{Fore.YELLOW} 🎮 MENYU                              {Fore.CYAN}│
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
                    if bot.is_night_time():
                        bot.wait_until_morning()
                    
                    bot.run_follow_cycle(20)
                    bot.show_stats()
                    
                    bot.check_and_unfollow()
                    bot.show_stats()
                    
                    logger.info("⏳ 1 soat kutilmoqda...")
                    time.sleep(3600)
                    
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
