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
import telegram_bot # State uchun


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
    
    def collect_followers(self, target: str, max_count: int = 1000) -> dict:
        """
        Target followerlarini bazaga to'plash (pending status bilan)
        Max 10,000 ta
        """
        max_count = min(max_count, 10000)  # Maximum 10k
        
        logger.info(f"\n{'='*50}")
        logger.info(f"📥 FOLLOWER TO'PLASH BOSHLANDI: @{target}")
        logger.info(f"🎯 Maqsad: {max_count} ta follower")
        logger.info(f"{'='*50}\n")
        
        result = {
            "target": target,
            "total_found": 0,
            "new_added": 0,
            "already_in_db": 0,
            "errors": 0
        }
        
        try:
            # Target profilga o'tish
            self.page.goto(f"https://www.instagram.com/{target}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)  # Server sekin - ko'proq kutish
            
            # Followers tugmasini bosish
            followers_btn = self.page.locator('a[href$="/followers/"]').first
            followers_btn.click()
            time.sleep(5)  # Server sekin - ko'proq kutish
            
            # Dialog ochilganini kutish
            dialog = self.page.locator('div[role="dialog"]').first
            dialog.wait_for(timeout=30000)  # 30 sek timeout
            time.sleep(5)  # Content yuklanishi uchun ko'proq vaqt
            
            # PageDown bilan dastlabki scroll (content yuklash uchun)
            for _ in range(3):
                self.page.keyboard.press("PageDown")
                time.sleep(0.5)
            time.sleep(3)
            
            collected = set()
            scroll_count = 0
            MAX_SCROLLS = 500  # Ko'p scroll (10k uchun)
            no_new_count = 0  # Yangi user topilmasa sanash
            
            while len(collected) < max_count and scroll_count < MAX_SCROLLS:
                # Linklar olish
                follower_links = dialog.locator('a')
                link_count = follower_links.count()
                
                new_in_scroll = 0
                
                for i in range(link_count):
                    if len(collected) >= max_count:
                        break
                    try:
                        href = follower_links.nth(i).get_attribute("href")
                        if not href or not href.startswith("/"):
                            continue
                        
                        username = href.strip("/").split("/")[0]
                        
                        # Validatsiya
                        if not username or len(username) < 2:
                            continue
                        if username in [target, 'explore', 'reels', 'stories', 'direct', 'accounts', config.INSTAGRAM_USERNAME]:
                            continue
                        
                        if username not in collected:
                            collected.add(username)
                            result["total_found"] += 1
                            
                            # Bazaga saqlash
                            if database.add_pending_user(username):
                                result["new_added"] += 1
                                new_in_scroll += 1
                            else:
                                result["already_in_db"] += 1
                    except:
                        continue
                
                # Progress log
                if scroll_count % 10 == 0:
                    logger.info(f"📊 Progress: {len(collected)}/{max_count} topildi, {result['new_added']} yangi qo'shildi")
                
                # Yangi user topilmadimi?
                if new_in_scroll == 0:
                    no_new_count += 1
                    if no_new_count >= 10:  # 10 scroll yangi user bo'lmasa to'xtash
                        logger.info("⚠️ 10 scrollda yangi user topilmadi, to'xtatilmoqda...")
                        break
                else:
                    no_new_count = 0
                
                # Scroll
                try:
                    self.page.evaluate("""() => {
                        const dialog = document.querySelector('div[role="dialog"]');
                        if (dialog) {
                            const divs = dialog.querySelectorAll('div');
                            for (const div of divs) {
                                if (div.scrollHeight > div.clientHeight) {
                                    div.scrollTop += 800;
                                    break;
                                }
                            }
                        }
                    }""")
                    time.sleep(1)
                except:
                    pass
                
                scroll_count += 1
            
            # Dialogni yopish
            self.page.keyboard.press("Escape")
            time.sleep(1)
            
            logger.info(f"\n{'='*50}")
            logger.info(f"✅ TO'PLASH TUGADI!")
            logger.info(f"📊 Jami topildi: {result['total_found']}")
            logger.info(f"✅ Yangi qo'shildi: {result['new_added']}")
            logger.info(f"♻️ Bazada bor edi: {result['already_in_db']}")
            logger.info(f"{'='*50}\n")
            
            # Backup
            try:
                import backup
                backup.backup_to_gist()
                logger.info("💾 Backup saqlandi")
            except:
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Collect xatosi: {e}")
            result["errors"] += 1
            return result
    
    def _is_logged_in(self) -> bool:
        """Login holatini tekshirish"""
        try:
            # Profile link bormi?
            profile_link = self.page.locator(f'a[href="/{config.INSTAGRAM_USERNAME}/"]')
            return profile_link.count() > 0
        except:
            return False
    
    def get_followers_of_target(self, count: int = 30, target: str = None) -> list:
        """Target akkauntning followerlarini olish"""
        if target is None:
            target = config.TARGET_ACCOUNT
        
        logger.info(f"🎯 @{target} followerlarini olmoqda...")
        
        try:
            # Target profilga o'tish
            self.page.goto(f"https://www.instagram.com/{target}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)  # Server sekin - ko'proq kutish
            
            # Followers tugmasini bosish
            followers_link = self.page.locator('a[href$="/followers/"]').first
            followers_link.click()
            time.sleep(5)  # Server sekin - ko'proq kutish
            
            # Dialog ochilishini kutish
            dialog = self.page.locator('div[role="dialog"]').first
            dialog.wait_for(timeout=30000)
            time.sleep(5)  # Content yuklanishi uchun
            
            # PageDown bilan dastlabki scroll (content yuklash uchun)
            for _ in range(3):
                self.page.keyboard.press("PageDown")
                time.sleep(0.5)
            time.sleep(3)
            
            # Deep Scroll Logic
            users = []
            scroll_count = 0
            MAX_SCROLLS = 100 # Chuqur qidirish
            
            logger.info("🔍 Deep Scroll boshlandi: Faqat yangi (bazada yo'q) userlar qidirilmoqda...")
            
            seen_usernames = set()  # Takroriy tekshiruvni tezlashtirish
            
            while len(users) < count and scroll_count < MAX_SCROLLS:
                dialog = self.page.locator('div[role="dialog"]').first
                
                # Dialog content yuklanishini kutish
                if scroll_count == 0:
                    time.sleep(3)  # Dastlabki yuklanish uchun
                
                # Barcha linklar (avvalgi ishlaydigan usul)
                follower_links = dialog.locator('a')
                current_batch_count = follower_links.count()
                
                # Debug: nechta link topildi
                if scroll_count == 0:
                    logger.info(f"📊 Dialog da {current_batch_count} ta link topildi")
                    if current_batch_count == 0:
                        # Yana bir oz kutib ko'ramiz
                        time.sleep(3)
                        follower_links = dialog.locator('a')
                        current_batch_count = follower_links.count()
                        logger.info(f"📊 Qayta urinish: {current_batch_count} ta link")
                
                new_in_this_scroll = 0
                skipped_in_db = 0
                skipped_invalid = 0

                for i in range(current_batch_count):
                    if len(users) >= count:
                        break
                    try:
                        href = follower_links.nth(i).get_attribute("href")
                        if not href or not href.startswith("/"):
                            continue
                            
                        # Username ajratish
                        username = href.strip("/").split("/")[0]
                        
                        # Validatsiya
                        if not username or len(username) < 2:
                            skipped_invalid += 1
                            continue
                        if username == target or username in ['explore', 'reels', 'stories', 'direct', 'accounts']:
                            skipped_invalid += 1
                            continue
                        
                        # 1. Shu scrollda ko'rilganmi?
                        if username in seen_usernames:
                            continue
                        seen_usernames.add(username)
                        
                        # 2. Bazada bormi?
                        if database.get_user(username):
                            skipped_in_db += 1
                            continue
                            
                        # Yangi topildi!
                        users.append(username)
                        new_in_this_scroll += 1
                        
                    except Exception as e:
                        continue
                
                # Debug logging
                if skipped_in_db > 0 or skipped_invalid > 0:
                    logger.info(f"📊 Scroll #{scroll_count}: +{new_in_this_scroll} yangi, {skipped_in_db} bazada bor, {skipped_invalid} noto'g'ri")
                
                if len(users) >= count:
                    logger.info(f"✅ Yetarlicha yangi user topildi: {len(users)} ta")
                    break
                
                # Scroll - Multiple methods
                try:
                    # Method 1: Dialog ichidagi barcha divlarni scroll qilish
                    scroll_success = self.page.evaluate("""() => {
                        const dialog = document.querySelector('div[role="dialog"]');
                        if (!dialog) return false;
                        
                        // Instagram'ning scrollable containerini topish
                        const containers = dialog.querySelectorAll('div');
                        let scrolled = false;
                        
                        for (const div of containers) {
                            // Scrollable bo'lsa
                            if (div.scrollHeight > div.clientHeight) {
                                const before = div.scrollTop;
                                div.scrollTop += 500;
                                if (div.scrollTop > before) {
                                    scrolled = true;
                                    break;
                                }
                            }
                        }
                        return scrolled;
                    }""")
                    
                    if not scroll_success:
                        # Method 2: Keyboard scroll (PageDown)
                        try:
                            dialog.click()
                            time.sleep(0.3)
                            for _ in range(3):
                                self.page.keyboard.press("PageDown")
                                time.sleep(0.2)
                        except:
                            pass
                    
                    if not scroll_success:
                        # Method 3: Mouse wheel directly on dialog
                        try:
                            box = dialog.bounding_box()
                            if box:
                                self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                                self.page.mouse.wheel(0, 1000)
                        except:
                            pass
                    
                    logger.info(f"🖱️ Scroll #{scroll_count}: {len(users)}/{count} yangi user topildi")
                    time.sleep(1.5)  # Yangi content yuklanishi uchun
                    
                except Exception as e:
                    logger.warning(f"⚠️ Scroll xatosi: {e}")
                    # Xato bo'lsa ham davom etamiz
                    time.sleep(1)
                
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
        if user and user['status'] != 'pending':
            logger.info(f"⏭️ @{username} allaqachon bazada (Status: {user['status']})")
            return False
        
        try:
            # Profilga o'tish
            logger.info(f"🔍 Profilga kirilmoqda: @{username}")
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
                
                # Har 5 ta followdan keyin backup (tez-tez saqlash, lekin API limitga yetmaslik)
                if daily_follow % 5 == 0:
                    try:
                        import backup
                        backup.backup_to_gist()
                        logger.info("💾 Avtomatik backup (har 5 ta follow)")
                    except Exception as e:
                        logger.warning(f"⚠️ Backup xatosi: {e}")
                
                return True
            else:
                return False
            
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                raise e
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
    
    def smart_sleep(self, seconds: int) -> bool:
        """Kutish davomida buyruqlarni tekshirish. Agar buyruq o'zgarsa True qaytaradi."""
        slept = 0
        while slept < seconds:
            time.sleep(1)
            slept += 1
            if slept % 2 == 0: # Har 2 sekundda tekshirish
                 current = database.get_config("current_cycle")
                 # Agar biz 'cleanup' da bo'lsak va 'stories' yoki 'auto' kelsa... 
                 # Unfollow paytida faqat 'auto' yoki 'cleanup' ruxsat etiladi. 'stories' kelishi bilan to'xtash kerak.
                 if current not in ['cleanup', 'auto']: 
                     logger.info(f"⚡ Kutish to'xtatildi! Yangi buyruq: {current}")
                     return True
        return False

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
        # Unfollow
        for username in to_unfollow:
            # 0. Buyruqni tekshirish
            if database.get_config("current_cycle") not in ['cleanup', 'auto']:
                 logger.info("⚡ Unfollow to'xtatildi (Yangi buyruq)")
                 break

            if self.unfollow_user(username):
                delay = self.get_human_delay(config.UNFOLLOW_DELAY_MIN, config.UNFOLLOW_DELAY_MAX)
                logger.info(f"⏳ {delay} sekund kutilmoqda...")
                # Smart sleep: Agar True qaytarsa (buyruq o'zgarsa), siklni buzamiz
                if self.smart_sleep(delay):
                    break
    
    def get_my_following(self) -> set:
        """Biz follow qilgan odamlarni olish (Following list)"""
        logger.info("📋 Following ro'yxati olinmoqda...")
        try:
            # O'z profilga o'tish
            self.page.goto(f"https://www.instagram.com/{config.INSTAGRAM_USERNAME}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
            # Following tugmasini bosish
            following_link = self.page.locator('a[href$="/following/"]').first
            following_link.click()
            time.sleep(3)
            
            following = set()
            scroll_count = 0
            prev_count = 0
            
            while scroll_count < 50:  # Max 50 scroll
                following_links = self.page.locator('div[role="dialog"] a[href^="/"]')
                
                for i in range(following_links.count()):
                    try:
                        href = following_links.nth(i).get_attribute("href")
                        if href and href.startswith("/"):
                            username = href.strip("/").split("/")[0]
                            if username and username != config.INSTAGRAM_USERNAME:
                                following.add(username)
                    except:
                        continue
                
                # Scroll
                try:
                    self.page.mouse.wheel(0, 3000)
                    time.sleep(1)
                except:
                    pass
                
                scroll_count += 1
                if len(following) == prev_count:
                    break
                prev_count = len(following)
            
            self.page.keyboard.press("Escape")
            time.sleep(1)
            
            logger.info(f"✅ {len(following)} ta following topildi")
            return following
            
        except Exception as e:
            logger.error(f"❌ Following olishda xato: {e}")
            return set()
    
    def cleanup_following(self) -> dict:
        """
        To'liq Following tozalash - 
        Sizga follow qilmagan barcha odamlarni unfollow qilish
        """
        logger.info(f"\n{'='*50}")
        logger.info("🧹 FOLLOWING CLEANUP BOSHLANDI")
        logger.info(f"{'='*50}\n")
        
        result = {
            "following_count": 0,
            "followers_count": 0,
            "non_followers": 0,
            "unfollowed": 0,
            "errors": 0
        }
        
        # 1. Following ro'yxatini olish
        my_following = self.get_my_following()
        result["following_count"] = len(my_following)
        
        if not my_following:
            logger.warning("⚠️ Following bo'sh yoki olib bo'lmadi")
            return result
        
        # 2. Followers ro'yxatini olish
        my_followers = self.get_my_followers()
        result["followers_count"] = len(my_followers)
        
        # 3. Sizga follow qilmaganlarni topish
        non_followers = my_following - my_followers
        result["non_followers"] = len(non_followers)
        
        logger.info(f"\n📊 Natija:")
        logger.info(f"   Following: {len(my_following)}")
        logger.info(f"   Followers: {len(my_followers)}")
        logger.info(f"   👎 Non-followers: {len(non_followers)}")
        
        if not non_followers:
            logger.info("✅ Barcha following sizga ham follow qilgan!")
            return result
        
        # 4. Unfollow qilish (limit bilan)
        logger.info(f"\n🚫 {len(non_followers)} ta odamni unfollow qilinmoqda...")
        
        unfollowed = 0
        for username in list(non_followers)[:config.DAILY_UNFOLLOW_LIMIT]:
            _, daily_unfollow = database.get_today_stats()
            if daily_unfollow >= config.DAILY_UNFOLLOW_LIMIT:
                logger.warning("⚠️ Kunlik unfollow limiti tugadi")
                break
            
            try:
                if self.unfollow_user(username):
                    unfollowed += 1
                    result["unfollowed"] += 1
                    
                    delay = self.get_human_delay(config.UNFOLLOW_DELAY_MIN, config.UNFOLLOW_DELAY_MAX)
                    logger.info(f"⏳ {delay} sekund kutilmoqda...")
                    time.sleep(delay)
            except Exception as e:
                logger.error(f"❌ @{username} unfollow xatosi: {e}")
                result["errors"] += 1
        
        logger.info(f"\n{'='*50}")
        logger.info(f"✅ CLEANUP TUGADI: {unfollowed} ta unfollow qilindi")
        logger.info(f"{'='*50}\n")
        
        return result
    
    def unfollow_user(self, username: str) -> bool:
        """Foydalanuvchini unfollow qilish (API + UI Fallback)"""
        import re
        import json
        
        _, daily_unfollow = database.get_today_stats()
        if daily_unfollow >= config.DAILY_UNFOLLOW_LIMIT:
            logger.warning(f"⚠️ Kunlik unfollow limiti tugadi")
            return False
        
        try:
            logger.info(f"⏳ Profilga o'tilmoqda: @{username}")
            # 1. Profilga o'tish (Timeout 30s ga kamaytirildi)
            try:
                self.page.goto(f"https://www.instagram.com/{username}/", timeout=30000)
                time.sleep(3)
                
                # 1.5 TEZKOR TEKSHIRUV: Balki allaqachon unfollow qilingandir?
                # Agar "Follow" tugmasi bo'lsa, API chaqirib o'tirmaymiz.
                head_check = self.page.locator('header section').first
                if not head_check.is_visible(): head_check = self.page.locator('main header').first
                
                check_btn = head_check.locator('button').filter(has_text=re.compile(r"Follow|Obuna bo'lish|Подписаться|Takip et", re.IGNORECASE)).first
                if check_btn.is_visible():
                    logger.info(f"ℹ️ @{username} allaqachon unfollow qilingan (Follow tugmasi bor)")
                    database.update_status(username, 'unfollowed')
                    return False

            except Exception as e:
                logger.warning(f"⚠️ Profil yuklashda timeout (lekin davom etamiz): {e}")

            logger.info(f"🔍 User ID qidirilmoqda: @{username}")
            # 2. User ID ni olish (JavaScript orqali)
            user_id = None
            # 2. User ID ni olish (JavaScript orqali)
            user_id = None
            try:
                # Method 1: API orqali (Eng ishonchli)
                profile_json_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
                user_id = self.page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch("{profile_json_url}", {{
                            headers: {{ 
                                "X-IG-App-ID": "936619743392459",
                                "X-Requested-With": "XMLHttpRequest"
                            }}
                        }});
                        const data = await resp.json();
                        return data.data.user.id;
                    }} catch(e) {{ return null; }}
                }}""")
                
                # Method 2: Meta taglardan (Fallback)
                if not user_id:
                     user_id = self.page.locator('meta[property="instapp:owner_user_id"]').get_attribute('content')
            except Exception as e:
                logger.warning(f"⚠️ User ID olishda xato: {e}")
            
            # 3. API orqali Unfollow (Tugma bosishsiz!)
            if user_id:
                logger.info(f"🔧 API Unfollow: @{username} (ID: {user_id})")
                
                # API chaqirish va natijani olish
                api_result = self.page.evaluate(f"""async () => {{
                    try {{
                        const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
                        const response = await fetch("https://www.instagram.com/api/v1/friendships/destroy/{user_id}/", {{
                            method: "POST",
                            headers: {{
                                "Content-Type": "application/x-www-form-urlencoded",
                                "X-CSRFToken": csrfToken,
                                "X-IG-App-ID": "936619743392459",
                                "X-Requested-With": "XMLHttpRequest"
                            }},
                            credentials: "include"
                        }});
                        const data = await response.json();
                        return {{ ok: response.ok, status: data.status, following: data.following }};
                    }} catch(e) {{ return {{ ok: false, error: e.toString() }}; }}
                }}""")
                
                logger.info(f"📨 API Response: {api_result}")
                
                # Natijani tekshirish
                # Status 'ok' bo'lsa, demak so'rov ketdi. 'following' ba'zida None keladi.
                if api_result and api_result.get('status') == 'ok':
                    logger.info("✅ API javobi OK. Natijani tekshirish uchun sahifa yangilanmoqda...")
                    
                    # Tasdiqlash: Sahifani yangilab, "Follow" tugmasi borligini tekshirish
                    try:
                        self.page.reload()
                        time.sleep(3)
                        
                        # Buttonni kengroq qidirish (nafaqat header ichida)
                        follow_btn = self.page.locator('button').filter(has_text=re.compile(r"Follow|Obuna bo'lish|Подписаться|Takip et", re.IGNORECASE)).first
                        
                        if follow_btn.is_visible():
                            database.update_status(username, 'unfollowed')
                            _, daily_unfollow = database.get_today_stats()
                            logger.info(f"{Fore.RED}🚫 Unfollow TASDIQLANDI: @{username} [{daily_unfollow}/{config.DAILY_UNFOLLOW_LIMIT}]")
                            return True
                        else:
                            # Balki hali ham "Following" tur gandir?
                            following_check = self.page.locator('button').filter(has_text=re.compile(r"Following|Requested|Obuna bo'lingan", re.IGNORECASE)).first
                            if following_check.is_visible():
                                logger.warning(f"⚠️ API 'ok' dedi, lekin hali ham 'Following' turibdi @{username}")
                            else:
                                logger.warning(f"⚠️ Sahifada na Follow, na Following tugmasi topildi @{username}")
                    except Exception as verify_error:
                         logger.warning(f"⚠️ Verifikatsiya xatosi: {verify_error}")

                else:
                    logger.warning(f"⚠️ API Unfollow muvaffaqiyatsiz @{username}: {api_result}. UI ga o'tilmoqda...")
            
            # 4. FALLBACK: UI orqali Unfollow (Eski usul)
            # Header section topish
            header_section = self.page.locator('header section').first
            if not header_section.is_visible():
                header_section = self.page.locator('main header').first
            
            # Following tugmasi
            following_btn = header_section.locator('button').filter(has_text=re.compile(r"Following|Requested|Подписки|Запрос|Obuna bo'lingan|So'rov yuborilgan|Takip", re.IGNORECASE)).first
            
            if not following_btn.is_visible():
                # Follow tugmasi bormi?
                follow_btn = header_section.locator('button').filter(has_text=re.compile(r"Follow|Obuna bo'lish|Подписаться|Takip et", re.IGNORECASE)).first
                
                if follow_btn.is_visible():
                    logger.info(f"⏭️ @{username} allaqachon unfollow qilingan")
                    database.update_status(username, 'unfollowed')
                    return False
                else:
                    all_text = header_section.inner_text()
                    clean_text = all_text.replace('\n', ' ')
                    logger.warning(f"⚠️ Headerda tugma topilmadi @{username}. Header: {clean_text[:100]}")
                    return False
            
            # Tugmani bosish
            following_btn.click(force=True)
            time.sleep(2)
            
            # Modal
            dialog = self.page.locator('div[role="dialog"]')
            if not dialog.is_visible():
                 following_btn.click(force=True)
                 time.sleep(2)
            
            # Unfollow tugmasi
            unfollow_btn = dialog.locator('button').filter(has_text=re.compile(r"Unfollow|Отменить|Obunani bekor qilish|Takibi Bırak|Bekor qilish", re.IGNORECASE)).first
            
            if unfollow_btn.is_visible():
                unfollow_btn.click()
                time.sleep(2)
                
                database.update_status(username, 'unfollowed')
                _, daily_unfollow = database.get_today_stats()
                logger.info(f"{Fore.RED}🚫 Unfollow: @{username} [{daily_unfollow}/{config.DAILY_UNFOLLOW_LIMIT}]")
                return True
            else:
                if dialog.is_visible():
                    dialog_text = dialog.inner_text()
                    all_btns = dialog.locator('button').all_inner_texts()
                    logger.warning(f"⚠️ Unfollow modali: Tugma yo'q. Dialog: {dialog_text[:50]}... Btns: {all_btns}")
                else:
                    logger.warning(f"⚠️ Unfollow modali umuman chiqmadi @{username}")
                    
                return False
                
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                raise e
            logger.error(f"❌ Unfollow xatosi @{username}: {e}")
            return False
    
    def watch_stories_and_like(self, duration: int):
        """
        Storylarni tomosha qilish va like bosish (Human-Like Behavior)
        Sleep o'rniga ishlatiladi.
        """
        import re
        logger.info(f"🍿 Story tomosha qilish rejimi: {duration} sekund...")
        
        start_time = time.time()
        
        try:
            # 1. Bosh sahifaga o'tish
            if self.page.url != "https://www.instagram.com/":
                self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                time.sleep(3)
            
            # 2. Story tray topish va birinchi storyni ochish
            # Eng ishonchli usul: <canvas> elementlari (Storyning rangli aylanasi)
            # Ular tilga bog'liq emas.
            story_rings = self.page.locator('canvas')
            ring_count = story_rings.count()
            
            if ring_count > 0:
                logger.info(f"✅ {ring_count} ta story (canvas) topildi.")
                # Odatda 1-chi canvas = O'zimizning story (Add Story)
                # 2-chi canvas = Birinchi do'stimizning storysi
                if ring_count > 1:
                    story_rings.nth(1).click()
                else:
                    story_rings.first.click()
                
                time.sleep(3) # Ochilishini kutish
            else:
                # Fallback: Text orqali qidirish (eski usul)
                stories = self.page.locator('div[role="button"]').filter(has_text=re.compile(r"Story|Hikoya|История", re.IGNORECASE))
                if stories.count() > 0:
                    stories.first.click()
                    time.sleep(2)
                else:
                    logger.warning("⚠️ Storylar topilmadi (Canvas yoki Text yo'q). Shunchaki kutilmoqda...")
                    time.sleep(duration)
                    return

            # 3. Loop: Story ko'rish va like bosish
            while (time.time() - start_time) < duration:
                # Qancha vaqt qoldi?
                remaining = duration - (time.time() - start_time)
                if remaining <= 0:
                    break
                
                # Bitta storyni ko'rish vaqti (3-10 sekund)
                watch_time = min(random.randint(3, 10), remaining)
                # Usernameni aniqlash (Retry bilan)
                current_username = "Noma'lum"
                for _ in range(3): # 3 marta urinib ko'rish
                    try:
                         # 1-usul: URL
                         url = self.page.url
                         match = re.search(r"stories/([^/]+)/", url)
                         if match:
                             current_username = match.group(1)
                             break # Topildi!
                         
                         # 2-usul: Header URL (Fallback)
                         if current_username == "Noma'lum":
                             user_el = self.page.locator('header a').first
                             if user_el.is_visible():
                                 current_username = user_el.inner_text()
                                 if current_username != "Noma'lum": break
                         
                         # 3-usul: Text
                         if current_username == "Noma'lum":
                             header_text = self.page.locator('header').first.inner_text()
                             lines = header_text.split('\n')
                             if lines:
                                 current_username = lines[0]
                                 if current_username != "Noma'lum": break
                    except:
                        pass
                    
                    time.sleep(0.5) # URL yangilanishini kutish

                logger.info(f"👀 Story ko'rilmoqda: @{current_username} ({watch_time}s)")
                
                # Telegramga yozish (Noma'lum bo'lsa ham)
                # Keshda bormi?
                if not hasattr(self, 'last_seen_story_user') or self.last_seen_story_user != current_username:
                     msg_text = f"👀 <b>Story ko'rilmoqda:</b> "
                     if current_username != "Noma'lum":
                         msg_text += f"<a href='https://instagram.com/{current_username}'>@{current_username}</a>"
                     else:
                         msg_text += "<i>(Yashirin profi)</i>"
                         
                     self.send_telegram_msg(msg_text)
                     self.last_seen_story_user = current_username

                # 0. Buyruqni tekshirish (Loop ichida)
                current_cycle_check = database.get_config("current_cycle", "auto")
                if current_cycle_check == 'cleanup':
                     logger.info("⚡ Story ko'rish to'xtatildi (Cleanup buyrug'i)")
                     break

                time.sleep(watch_time)
                
                # Random Like (100% ehtimol - Test uchun)
                if random.random() < 1.0:
                    try:
                        # 1. AVVAL TEKSHIRAMIZ: Allaqaqchon like bosilganmi?
                        unlike_selector = (
                            'svg[aria-label*="Unlike"], '
                            'svg[aria-label*="O\'chirish"], '
                            'svg[aria-label*="Yoqtirishni bekor qilish"], '
                            'svg[aria-label*="Vazgeç"], '
                            'svg[aria-label*="Je n\'aime plus"]'
                        )
                        if self.page.locator(unlike_selector).first.is_visible():
                            logger.info(f"ℹ️ {current_username}: Storyga allaqachon like bosilgan.")
                        else:
                            # Like bosish
                            like_selector = (
                                'svg[aria-label*="Like"], '
                                'svg[aria-label*="like"], '
                                'svg[aria-label*="Нравится"], '
                                'svg[aria-label*="Yoqtirish"], '
                                'svg[aria-label*="Beğen"], '
                                'svg[aria-label*="J\'aime"]'
                            )
                            
                            like_svgs = self.page.locator(like_selector)
                            count = like_svgs.count()
                            clicked = False
                            
                            for i in range(count):
                                svg = like_svgs.nth(i)
                                if svg.is_visible():
                                    like_btn = svg.locator("..")
                                    like_btn.click(force=True)
                                    clicked = True
                                    logger.info(f"{Fore.MAGENTA}❤️ Storyga Like bosildi!")
                                    self.send_telegram_msg(f"❤️ <b>Storyga Like bosildi:</b> <a href='https://instagram.com/{current_username}'>@{current_username}</a>")
                                    time.sleep(1)
                                    break
                        
                        if not clicked:
                             # DEBUG: Tugma topilmadi
                             try:
                                 if not hasattr(self, 'debug_sent'):
                                     # SVG dagi barcha aria-label larni olib ko'ramiz (Filtrsiz)
                                     all_labels = self.page.locator('svg[aria-label]').evaluate_all("els => els.map(e => e.getAttribute('aria-label'))")
                                     # Faqat qisqa va bo'sh bo'lmaganlarini olamiz
                                     readable_labels = [str(l) for l in all_labels if l and len(l) < 30] 
                                     
                                     logger.warning(f"⚠️ Like topilmadi. Mavjud: {readable_labels}")
                                     # Telegramga hammasini jo'natamiz
                                     if readable_labels:
                                         self.send_telegram_msg(f"⚠️ <b>DEBUG (Like topilmadi):</b>\nEkranda: {', '.join(readable_labels)}")
                                         self.debug_sent = True
                             except Exception as e:
                                 logger.error(f"Debug Error: {e}")
                    except Exception as e:
                        logger.error(f"Like Error: {e}")
                
                # Keyingi storyga o'tish (Next tugmasi yoki Keyboard Right)
                try:
                    self.page.keyboard.press("ArrowRight")
                    time.sleep(0.5)
                except:
                    break
                    
                # Agar storylar tugagan bo'lsa (Home sahifasiga qaytgan bo'lsa)
                if self.page.url == "https://www.instagram.com/":
                    logger.info("✅ Barcha storylar ko'rildi.")
                    break

        except Exception as e:
            logger.error(f"❌ Story ko'rishda xato: {e}")
            
        # Agar vaqt ortib qolsa - shunchaki kutish
        remaining = duration - (time.time() - start_time)
        if remaining > 0:
            logger.info(f"⏳ Qolgan vaqt: {int(remaining)}s kutilmoqda...")
            time.sleep(remaining)
            
    def send_telegram_msg(self, text: str):
        """Telegramga xabar yuborish (Requests orqali - Conflict bo'lmaydi)"""
        import requests
        try:
            # config.ADMIN_IDS birinchi adminiga
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
    
    def run_follow_cycle(self, count: int = 20, target: str = None):
        """Follow sikli"""
        # Multi-target: random target tanlash
        if target is None:
            from pathlib import Path
            targets_file = Path("targets.json")
            if targets_file.exists():
                try:
                    import json
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
                try:
                    # 1. State tekshirish (Bazadan)
                    current_cycle = database.get_config("current_cycle", "auto")
                    collect_target = database.get_config("collect_target")
                    collect_count_str = database.get_config("collect_count", "1000")
                    collect_count = int(collect_count_str) if collect_count_str.isdigit() else 1000
                    
                    logger.info(f"🔄 CYCLE CHECK: {current_cycle} (Target: {collect_target})")

                    # ==========================================
                    # ♻️ SIKL TURLARI BO'YICHA ISHLASH
                    # ==========================================
                    
                    # ------------------------------------------
                    # MODE 1: COLLECT (Yig'ish)
                    # ------------------------------------------
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

                    # ------------------------------------------
                    # MODE 2: CLEANUP (Tozalash)
                    # ------------------------------------------
                    elif current_cycle == 'cleanup':
                        logger.info(f"\n{'='*40}")
                        logger.info("🧹 CLEANUP BOSHLANDI (Unfollow non-followers)")
                        logger.info(f"{'='*40}")
                        
                        bot.cleanup_following()
                        
                        logger.info("✅ Cleanup tugadi. Auto rejimga qaytilmoqda.")
                        database.set_config("current_cycle", "auto")

                    # ------------------------------------------
                    # MODE 3: STORIES (Faqat Story ko'rish)
                    # ------------------------------------------
                    elif current_cycle == 'stories':
                        logger.info(f"\n{'='*40}")
                        logger.info("🍿 STORY MODE BOSHLANDI")
                        logger.info(f"{'='*40}")
                        
                        # 1 soat davomida story ko'rish (yoki tugaguncha)
                        bot.watch_stories_and_like(3600)
                        
                        logger.info("✅ Story ko'rish tugadi. Auto rejimga qaytilmoqda.")
                        database.set_config("current_cycle", "auto")

                    # ------------------------------------------
                    # MODE 3: AUTO (Faqat Baza bilan ishlash)
                    # ------------------------------------------
                    else:
                        # 1. Follow (FAQAT Pending userlar)
                        pending_count = database.get_pending_count()
                        
                        if pending_count > 0:
                            logger.info(f"📋 Pending userlar mavjud: {pending_count} ta. Bazadan olinmoqda...")
                            pending_users = database.get_pending_users(20)
                            
                            count = 0
                            for user in pending_users:
                                # 0. Buyruqni tekshirish (Tezkor chiqish)
                                if database.get_config("current_cycle") != 'auto': 
                                     logger.info(f"⚡ Yangi buyruq keldi! Follow to'xtatildi.")
                                     break

                                if bot.follow_user(user):
                                    count += 1
                                    # Statusni update qilish (pending -> waiting)
                                    try:
                                        with database.get_connection() as conn:
                                            conn.execute("UPDATE users SET status = 'waiting', followed_at = ? WHERE username = ?", 
                                                       (datetime.now(), user))
                                            conn.commit()
                                        
                                        # Human Delay (Story Tomosha qilish)
                                        delay = bot.get_human_delay(config.FOLLOW_DELAY_MIN, config.FOLLOW_DELAY_MAX)
                                        logger.info(f"⏳ Keyingi followgacha: {delay} sekund...")
                                        
                                        # Sleep o'rniga Story ko'rish
                                        bot.watch_stories_and_like(delay)

                                    except Exception as e:
                                        logger.error(f"❌ DB Update error: {e}")
                                        
                            logger.info(f"✅ Pending userlardan {count} tasi follow qilindi")
                            
                        else:
                            # ⚠️ QIDIRUV YO'Q! (Database-First)
                            logger.info("💤 Baza bo'sh. Yangi userlar uchun /collect buyrug'ini ishlating.")
                            
                        bot.show_stats()
                        
                        # 2. Unfollow (24 soat o'tganlarni tekshirish)
                        bot.check_and_unfollow()
                        bot.show_stats()
                    
                    # ------------------------------------------
                    # DAM OLISH & BUYRUQLARNI KUTISH
                    # ------------------------------------------
                    # Agar buyruq o'zgargan bo'lsa (masalan stories), uxlashga yotmaymiz!
                    if database.get_config("current_cycle", "auto") != 'auto':
                        logger.info("⚡ Sikl o'tkazib yuborilmoqda (Yangi buyruq uchun)")
                        continue

                    wait_time = random.randint(3600, 7200) 
                    logger.info(f"⏳ Sikl tugadi. {wait_time/60:.1f} daqiqa kutilmoqda...")
                    
                    # Kutish davomida buyruqlarni tekshirish (har 5 sekund)
                    slept = 0
                    while slept < wait_time:
                        time.sleep(5)
                        slept += 5
                        
                        # Agar buyruq kelsa - kutishni buzamiz
                        new_cycle = database.get_config("current_cycle", "auto")
                        if new_cycle in ['collect', 'cleanup']:
                            logger.info(f"⚡ Yangi buyruq ({new_cycle})! Kutish to'xtatildi.")
                            break
                            
                except Exception as e:
                    logger.error(f"❌ Main loop xatosi: {e}")
                    if "Target page, context or browser has been closed" in str(e):
                         logger.critical("🔥 Browser yopilib qoldi! Qayta ishga tushirish uchun thread to'xtatilmoqda...")
                         break # Threadni tugatish (start.py qayta yoqadi)
                    time.sleep(60)
                
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

