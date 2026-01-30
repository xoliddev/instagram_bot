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
from datetime import datetime
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

# Modular imports
from instagram.api import InstagramAPI
from instagram.actions import InstagramActions
from instagram.stories import InstagramStories
from instagram.sync import InstagramSync
from instagram.utils import get_human_delay, update_heartbeat

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
        
        # Sub-modules (page yuklangandan keyin init bo'ladi)
        self.api = None
        self.actions = None
        self.stories = None
        self.sync = None

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
                headless=config.HEADLESS,
                args=["--no-sandbox", "--disable-setuid-sandbox"] if config.HEADLESS else [],
                viewport={"width": 1280, "height": 800},
                locale="en-US"
            )
            
            # Cookie'larni Gist dan yuklash (Koyeb uchun)
            try:
                import backup
                cookies = backup.restore_cookies_from_gist()
                if cookies:
                    self.context.add_cookies(cookies)
                    logger.info(f"🍪 Gist dan {len(cookies)} ta cookie yuklandi")
            except Exception as e:
                logger.warning(f"⚠️ Cookie yuklash xatosi: {e}")
            
            self.page = self.context.new_page()
            self.page.set_default_timeout(60000)
            
            # Resource blocking (Tezlashtirish)
            try:
                self.page.route("**/*", lambda route: route.abort() 
                    if route.request.resource_type in ["image", "media", "font"] 
                    else route.continue_())
                logger.info("⚡ Resource blocking yoqildi (Imagelar bloklandi)")
            except Exception as e:
                logger.warning(f"⚠️ Resource blocking xatosi: {e}")
            
            # Sub-modullarni init qilish
            self._init_modules()
            
            logger.info("✅ Brauzer tayyor")
            return True
            
        except Exception as e:
            logger.error(f"❌ Brauzer xatosi: {e}")
            return False

    def close(self):
        """Brauzerni yopish"""
        logger.info("❌ Brauzer yopilmoqda...")
        try:
            if self.page:
                try:
                    self.page.close()
                except:
                    pass
            if self.context:
                try:
                    self.context.close()
                except:
                    pass
            if self.playwright:
                try:
                    self.playwright.stop()
                except:
                    pass
        except Exception as e:
            logger.warning(f"⚠️ Brauzer yopishda xato: {e}")
        finally:
            self.page = None
            self.context = None
            self.playwright = None
            self.api = None
            self.actions = None
            self.stories = None
            self.sync = None
    
    def _init_modules(self):
        """Sub-modullarni ishga tushirish"""
        self.api = InstagramAPI(self.page, self.context)
        self.actions = InstagramActions(self.page, self.context)
        self.stories = InstagramStories(self.page, self.context)
        self.sync = InstagramSync(self.page, self.context)
    
    def restart_browser_full(self):
        """Brauzerni butunlay o'chirib qayta yoqish"""
        logger.warning("🔄 Brauzer to'liq restart qilinmoqda...")
        try:
            self.close()
            time.sleep(5)
            if self.start_browser():
                self.login()
                logger.info("✅ Brauzer restart qilindi")
            else:
                logger.error("❌ Brauzer restart qilmadi")
        except Exception as e:
            logger.error(f"❌ Restart xatosi: {e}")

    def login(self) -> bool:
        """Instagram'ga kirish"""
        logger.info("🔐 Instagram tekshirilmoqda...")
        
        try:
            # Clear stuck navigation
            if self.page.url != "about:blank":
                try:
                    self.page.goto("about:blank")
                    time.sleep(1)
                except:
                    pass

            logger.info("loading... (60s timeout)")
            try:
                self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
            except Exception as goto_err:
                try:
                    title = self.page.title()
                    if "Instagram" in title:
                         logger.info(f"⚠️ Timeout bo'ldi, lekin sahifa yuklanganga o'xshaydi: {title}")
                    else:
                         raise goto_err
                except:
                    raise goto_err

            logger.info("✅ Sayt yuklandi (yoki timeout)")
            
            # Qo'shimcha kutish (resurslar yuklanishi uchun)
            time.sleep(random.uniform(3, 5))
            
        except Exception as e:
            logger.warning(f"⚠️ Navigatsiya xatosi: {e}")
            try:
                self.page.screenshot(path="error_nav.png")
            except:
                pass
        
        logger.info("🔍 Login holati tekshirilmoqda...")
        if self._is_logged_in():
            logger.info(f"✅ Allaqachon login qilingan!")
            return True
        
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
            
            time.sleep(5)
            
            if self._is_logged_in():
                logger.info("✅ Login muvaffaqiyatli!")
                
                # Cookies ni Gist ga saqlash
                try:
                    import backup
                    cookies = self.context.cookies()
                    backup.backup_cookies_to_gist(cookies)
                except Exception as e:
                    logger.warning(f"⚠️ Cookie backup xatosi: {e}")
                
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
                logger.warning("⚠️ Login muvaffaqiyatsiz. Tekshiring...")
                return False
                
        except Exception as e:
            logger.error(f"❌ Login xatosi: {e}")
            return False
    
    def _is_logged_in(self) -> bool:
        """Login holatini tekshirish"""
        try:
            profile_link = self.page.locator(f'a[href="/{config.INSTAGRAM_USERNAME}/"]')
            return profile_link.count() > 0
        except:
            return False

    # ============ DELEGATED METHODS ============
    # Sub-modullardagi funksiyalarni chaqirish
    
    def follow_user(self, username: str) -> bool:
        """Foydalanuvchini follow qilish"""
        return self.actions.follow_user(username)
    
    def unfollow_user(self, username: str) -> bool:
        """Foydalanuvchini unfollow qilish"""
        return self.actions.unfollow_user(username)
    
    def check_and_unfollow(self):
        """24 soat o'tganlarni tekshirish va unfollow qilish"""
        self.actions.check_and_unfollow()
    
    def smart_cleanup_interactive(self):
        """Smart Cleanup - follow qaytarmaganlarni unfollow qilish"""
        self.actions.smart_cleanup_interactive()
    
    def watch_stories_and_like(self, duration: int, wait_remaining: bool = True):
        """Storylarni tomosha qilish va like bosish"""
        self.stories.watch_stories_and_like(duration, wait_remaining)
    
    def sync_my_followers(self):
        """Followerlarni sinxronlash"""
        self.sync.sync_my_followers()
    
    def collect_followers(self, target: str, max_count: int = 1000) -> dict:
        """Target followerlarini to'plash"""
        return self.sync.collect_followers(target, max_count)
    
    def get_followers_of_target(self, count: int = 30, target: str = None) -> list:
        """Target followerlarini olish"""
        return self.sync.get_followers_of_target(count, target)
    
    def run_follow_cycle(self, count: int = 20, target: str = None):
        """Follow sikli"""
        # Multi-target: random target tanlash
        if target is None:
            targets_file = Path("targets.json")
            if targets_file.exists():
                try:
                    with open(targets_file, 'r') as f:
                        targets = json.load(f)
                    if targets:
                        target = random.choice(targets)
                        logger.info(f"🎲 Tasodifiy target tanlandi: @{target}")
                except:
                    pass
            if target is None:
                target = config.TARGET_ACCOUNT
        
        logger.info(f"\n{'='*50}")
        logger.info(f"🚀 FOLLOW SIKLI BOSHLANDI - Target: @{target}")
        logger.info(f"{'='*50}\n")
        
        users = self.get_followers_of_target(count, target)
        
        if not users:
            logger.warning("⚠️ Foydalanuvchi topilmadi")
            return
        
        followed = 0
        for username in users:
            if self.follow_user(username):
                followed += 1
                delay = get_human_delay(config.FOLLOW_DELAY_MIN, config.FOLLOW_DELAY_MAX)
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
        if not config.HEADLESS:
            try:
                input("Login qilganingizdan keyin ENTER bosing...")
            except:
                pass
            
        if not bot._is_logged_in():
            print(f"{Fore.RED}❌ Hali ham login bo'lmagan. Dastur tugatildi.")
            bot.close()
            return
    
    # Server rejimi (24/7)
    if config.HEADLESS:
        logger.info("🤖 Server rejimi aniqlandi: 24/7 Avtomatik rejim ishga tushmoqda...")
        print(f"\n{Fore.YELLOW}🤖 AVTOMATIK REJIM (24/7) - Server")
        
        # Server startda followerlarni sinxronlash
        bot.sync_my_followers()
        
        # State tiklash (Agar oldin biror ish qilayotgan bo'lsa, davom ettiradi)
        saved_cycle = database.get_config("current_cycle")
        if saved_cycle and saved_cycle != "auto":
             logger.info(f"🔄 Oldingi holat tiklandi: {saved_cycle}")
        else:
             logger.info("🔄 Auto rejimga o'tilmoqda")
             database.set_config("current_cycle", "auto")
             database.set_config("strict_mode", "false")
        
        last_sync_time = datetime.now()
        
        try:
            while True:
                update_heartbeat()
                try:
                    # Har soatlik sync
                    hours_since_sync = (datetime.now() - last_sync_time).total_seconds() / 3600
                    if hours_since_sync >= 1:
                        logger.info("🔄 Har soatlik sync: Yangi followerlar tekshirilmoqda...")
                        bot.sync_my_followers()
                        last_sync_time = datetime.now()
                    
                    # State tekshirish
                    current_cycle = database.get_config("current_cycle", "auto")
                    collect_target = database.get_config("collect_target")
                    collect_count_str = database.get_config("collect_count", "1000")
                    collect_count = int(collect_count_str) if collect_count_str.isdigit() else 1000
                    
                    logger.info(f"🔄 CYCLE CHECK: {current_cycle} (Target: {collect_target})")

                    # SIKL TURLARI
                    if current_cycle == 'collect':
                        if collect_target:
                            logger.info(f"\n{'='*40}")
                            logger.info(f"📥 COLLECT BOSHLANDI: @{collect_target} ({collect_count} ta)")
                            logger.info(f"{'='*40}")
                            
                            bot.collect_followers(collect_target, collect_count)
                            
                            logger.info("✅ Collect tugadi. Auto rejimga qaytilmoqda.")
                            database.set_config("current_cycle", "auto")
                            database.set_config("collect_target", "")
                        else:
                            logger.warning("⚠️ Collect target topilmadi")
                            database.set_config("current_cycle", "auto")

                    elif current_cycle == 'cleanup':
                        logger.info(f"\n{'='*40}")
                        logger.info("🧹 CLEANUP BOSHLANDI (Unfollow non-followers)")
                        logger.info(f"{'='*40}")
                        
                        bot.smart_cleanup_interactive()
                        
                        logger.info("✅ Cleanup tugadi. Auto rejimga qaytilmoqda.")
                        database.set_config("current_cycle", "auto")

                    elif current_cycle == 'stories':
                        logger.info(f"\n{'='*40}")
                        logger.info("🍿 STORY MODE BOSHLANDI")
                        logger.info(f"{'='*40}")
                        
                        bot.watch_stories_and_like(3600, wait_remaining=False)
                        
                        logger.info("✅ Story ko'rish tugadi. Darhol auto rejimga qaytilmoqda.")
                        database.set_config("current_cycle", "auto")

                    elif current_cycle == 'follow':
                        target = database.get_config("follow_target")
                        count = int(database.get_config("follow_count", "20"))
                        
                        logger.info(f"\n{'='*40}")
                        logger.info(f"🚀 FOLLOW CYCLE BOSHLANDI: @{target} ({count} ta)")
                        logger.info(f"{'='*40}")
                        
                        bot.run_follow_cycle(count, target)
                        
                        logger.info("✅ Follow sikli tugadi. Auto rejimga qaytilmoqda.")
                        database.set_config("current_cycle", "auto")

                    else:
                        # AUTO MODE
                        pending_count = database.get_pending_count()
                        
                        daily_follow, _ = database.get_today_stats()
                        if daily_follow >= config.DAILY_FOLLOW_LIMIT:
                            logger.info(f"💤 Kunlik follow limiti tugadi ({daily_follow}/{config.DAILY_FOLLOW_LIMIT}).")
                        elif pending_count > 0:
                            logger.info(f"📋 Pending userlar mavjud: {pending_count} ta. Bazadan olinmoqda...")
                            pending_users = database.get_pending_users(20)
                            
                            count = 0
                            for user in pending_users:
                                if database.get_config("current_cycle") != 'auto': 
                                    logger.info(f"⚡ Yangi buyruq keldi! Follow to'xtatildi.")
                                    break

                                if bot.follow_user(user):
                                    count += 1
                                    try:
                                        with database.get_connection() as conn:
                                            conn.execute("UPDATE users SET status = 'waiting', followed_at = ? WHERE username = ?", 
                                                       (datetime.now(), user))
                                            conn.commit()
                                        
                                        delay = get_human_delay(config.FOLLOW_DELAY_MIN, config.FOLLOW_DELAY_MAX)
                                        logger.info(f"⏳ Keyingi followgacha: {delay} sekund...")
                                        
                                        bot.watch_stories_and_like(delay)

                                    except Exception as e:
                                        logger.error(f"❌ DB Update error: {e}")
                                        
                            logger.info(f"✅ Pending userlardan {count} tasi follow qilindi")
                            
                        else:
                            random_target = database.get_random_target()
                            if random_target:
                                logger.info(f"🎲 Pending bo'sh. Random target tanlandi: @{random_target}")
                                bot.run_follow_cycle(20, random_target)
                            else:
                                logger.info("💤 Baza bo'sh va target yo'q. /add_target yoki /collect buyrug'ini ishlating.")
                            
                        bot.show_stats()
                        
                        # Unfollow
                        bot.check_and_unfollow()
                        bot.show_stats()
                    
                    # DAM OLISH
                    if database.get_config("current_cycle", "auto") != 'auto':
                        logger.info("⚡ Sikl o'tkazib yuborilmoqda (Yangi buyruq uchun)")
                        continue

                    wait_time = random.randint(3600, 7200) 
                    logger.info(f"⏳ Sikl tugadi. {wait_time/60:.1f} daqiqa davomida Story ko'riladi...")
                    
                    bot.watch_stories_and_like(wait_time)
                            
                except Exception as e:
                    logger.error(f"❌ Main loop xatosi: {e}")
                    if "Target page, context or browser has been closed" in str(e):
                         logger.critical("🔥 Browser yopilib qoldi! Qayta ishga tushirish uchun thread to'xtatilmoqda...")
                         break
                    time.sleep(60)
                
        except KeyboardInterrupt:
            logger.info("⚠️ To'xtatildi")
        finally:
            bot.close()
        return

    # Lokal menyu
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
