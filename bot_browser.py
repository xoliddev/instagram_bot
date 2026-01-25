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
    
    def safe_goto(self, url: str, timeout: int = 20000, retries: int = 2) -> bool:
        """Xavfsiz sahifaga o'tish - timeout va retry bilan"""
        for attempt in range(retries):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                return True
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(f"⚠️ Sahifa yuklanmadi ({attempt+1}/{retries}): {url[:50]}...")
                    time.sleep(3)
                else:
                    logger.error(f"❌ Sahifa yuklanmadi: {url[:50]}... - {str(e)[:50]}")
                    return False
        return False
    
    def refresh_page_if_stuck(self) -> bool:
        """Sahifa qotib qolsa yangilash"""
        try:
            self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            return True
        except:
            logger.warning("⚠️ Instagram asosiy sahifasi yuklanmadi")
            return False

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
            
            # 🍪 Cookie'larni Gist dan yuklash (Koyeb uchun)
            try:
                import backup
                cookies = backup.restore_cookies_from_gist()
                if cookies:
                    self.context.add_cookies(cookies)
                    logger.info(f"🍪 Gist dan {len(cookies)} ta cookie yuklandi")
            except Exception as e:
                logger.warning(f"⚠️ Cookie yuklash xatosi: {e}")
            
            self.page = self.context.new_page()
            self.page.set_default_timeout(60000) # 60 sekund timeout
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
            logger.info("loading... (30s timeout)")
            self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
            logger.info("✅ Sayt yuklandi (yoki timeout)")
        except Exception as e:
            logger.warning(f"⚠️ Navigatsiya xatosi: {e}")
            self.page.screenshot(path="error_nav.png")
            
        time.sleep(3)
        
        # Login holatini tekshirish
        logger.info("🔍 Login holati tekshirilmoqda...")
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
                
                # 🍪 Cookies ni Gist ga saqlash (restart dan keyin ham ishlashi uchun)
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
                # Challenge yoki xato bormi?
                logger.warning("⚠️ Login muvaffaqiyatsiz. Tekshiring...")
                return False
                
        except Exception as e:
            logger.error(f"❌ Login xatosi: {e}")
            return False
    
    def collect_followers(self, target: str, max_count: int = 1000) -> dict:
        """
        Target followerlarini bazaga to'plash (GraphQL API orqali)
        Max 10,000 ta
        """
        max_count = min(max_count, 10000)
        
        logger.info(f"\n{'='*50}")
        logger.info(f"📥 FOLLOWER TO'PLASH: @{target} (GraphQL API)")
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
            # 1. Target user ID olish
            target_user_id = self._get_target_user_id(target)
            
            if not target_user_id:
                logger.warning("⚠️ Target User ID olinmadi, UI scroll ga o'tilmoqda...")
                return self._collect_followers_ui_fallback(target, max_count)
            
            logger.info(f"✅ Target User ID: {target_user_id}")
            
            # 2. GraphQL API orqali followers olish
            followers = self._fetch_followers_api(target_user_id, max_count)
            
            if followers:
                logger.info(f"📥 API dan {len(followers)} ta follower olindi")
                
                for username in followers:
                    if database.add_pending_user(username):
                        result["new_added"] += 1
                    else:
                        result["already_in_db"] += 1
                    result["total_found"] += 1
                
                logger.info(f"\n{'='*50}")
                logger.info(f"✅ TO'PLASH TUGADI!")
                logger.info(f"📊 Jami topildi: {result['total_found']}")
                logger.info(f"✅ Yangi qo'shildi: {result['new_added']}")
                logger.info(f"♻️ Bazada bor edi: {result['already_in_db']}")
                logger.info(f"{'='*50}\n")
                
                try:
                    import backup
                    backup.backup_to_gist()
                    logger.info("💾 Backup saqlandi")
                except:
                    pass
                
                return result
            else:
                logger.warning("⚠️ API dan follower olinmadi, UI fallback...")
                return self._collect_followers_ui_fallback(target, max_count)
                
        except Exception as e:
            logger.error(f"❌ Collect xatosi: {e}")
            result["errors"] += 1
            return result
    
    def _get_target_user_id(self, target: str):
        """Target username dan user ID olish"""
        try:
            self.page.goto(f"https://www.instagram.com/{target}/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            user_id = self.page.evaluate("""() => {
                const html = document.documentElement.innerHTML;
                
                let match = html.match(/"profilePage_([0-9]+)"/);
                if (match) return match[1];
                
                match = html.match(/"user_id":"([0-9]+)"/);
                if (match) return match[1];
                
                match = html.match(/"logging_page_id":"profilePage_([0-9]+)"/);
                if (match) return match[1];
                
                return null;
            }""")
            
            return user_id
        except Exception as e:
            logger.error(f"❌ Target User ID olishda xato: {e}")
            return None
    
    def _collect_followers_ui_fallback(self, target: str, max_count: int) -> dict:
        """UI Scroll fallback (API ishlamasa)"""
        logger.info("🔄 UI Scroll fallback ishga tushdi...")
        
        result = {"target": target, "total_found": 0, "new_added": 0, "already_in_db": 0, "errors": 0}
        
        try:
            self.page.goto(f"https://www.instagram.com/{target}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            
            followers_btn = self.page.locator('a[href$="/followers/"]').first
            followers_btn.click()
            time.sleep(5)
            
            dialog = self.page.locator('div[role="dialog"]').first
            dialog.wait_for(timeout=30000)
            time.sleep(5)
            
            collected = set()
            scroll_count = 0
            no_new = 0
            IGNORE = {'explore', 'reels', 'stories', 'direct', 'accounts', config.INSTAGRAM_USERNAME, 'create', 'guide', target}
            
            while len(collected) < max_count and scroll_count < 200 and no_new < 10:
                links = dialog.locator('a')
                count = links.count()
                prev_len = len(collected)
                
                for i in range(count):
                    if len(collected) >= max_count:
                        break
                    try:
                        href = links.nth(i).get_attribute("href")
                        if href and href.startswith("/"):
                            u = href.strip("/").split("/")[0]
                            if u and len(u) >= 2 and u not in IGNORE and u not in collected:
                                collected.add(u)
                                if database.add_pending_user(u):
                                    result["new_added"] += 1
                                else:
                                    result["already_in_db"] += 1
                                result["total_found"] += 1
                    except:
                        pass
                
                if len(collected) == prev_len:
                    no_new += 1
                else:
                    no_new = 0
                
                self.page.evaluate("""() => {
                    const dialog = document.querySelector('div[role="dialog"]');
                    if (dialog) {
                        for (const div of dialog.querySelectorAll('div')) {
                            if (div.scrollHeight > div.clientHeight) {
                                div.scrollTop += 800;
                                break;
                            }
                        }
                    }
                }""")
                time.sleep(1.5)
                scroll_count += 1
                
                if scroll_count % 10 == 0:
                    logger.info(f"📊 UI Progress: {len(collected)}/{max_count}")
            
            self.page.keyboard.press("Escape")
            logger.info(f"✅ UI Fallback: {result['total_found']} ta topildi")
            
            try:
                import backup
                backup.backup_to_gist()
            except:
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"❌ UI Fallback xatosi: {e}")
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
        """Foydalanuvchini follow qilish (Retry va Timeout himoyasi bilan)"""
        
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
            
        # RETRY LOGIC (2 marta urinish)
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Random delay (Anti-Spam) - kamaytirildi
                time.sleep(random.uniform(1, 3))
                
                logger.info(f"🔍 Profilga kirilmoqda: @{username} (Urinish: {attempt+1}/{max_retries})")
                
                # Profilga o'tish (15s Timeout - commit = tezroq, hang bo'lmaydi)
                try:
                    self.page.goto(f"https://www.instagram.com/{username}/", wait_until="commit", timeout=15000)
                    # Qo'shimcha: DOM yuklanganliqini kutish (5s max)
                    try:
                        self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except:
                        pass  # Ignore - commit yetarli
                except Exception as goto_err:
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️ Timeout. 3s kutib qayta urinamiz...")
                        time.sleep(3)
                        continue
                    else:
                        logger.error(f"❌ Profil yuklanmadi @{username}: Timeout")
                        return False

                time.sleep(random.uniform(1, 2))
                
                # Follow tugmasini qidirish (5s timeout)
                follow_btn = self.page.locator('button:has-text("Follow")').first
                
                # Agar Follow tugmasi bo'lmasa
                if not follow_btn.is_visible():
                    # Balki allaqachon follow qilingandir? (Message yoki Requested)
                    if self.page.locator('div:has-text("Message")').first.is_visible() or \
                       self.page.locator('button:has-text("Requested")').first.is_visible():
                        logger.info(f"⏭️ @{username} allaqachon follow qilingan")
                        database.add_user(username) # Bazaga 'waiting' bo'lib tushadi
                        return False
                    
                    # Balki sahifa chala yuklangandir?
                    logger.warning(f"⚠️ @{username}: Follow tugmasi topilmadi (lekin profil mavjud). Skip.")
                    return False
                
                # Follow bosish
                follow_btn.click()
                time.sleep(2)

                # "Pending" popup tekshiruvi (Private accountlar)
                try:
                    pending_dialog = self.page.locator('div[role="dialog"]:has-text("pending")')
                    if pending_dialog.is_visible():
                        ok_btn = pending_dialog.locator('button:has-text("OK")')
                        if ok_btn.is_visible():
                            ok_btn.click()
                            time.sleep(1)
                except:
                    pass
                
                # Bazaga yozish
                if database.add_user(username):
                    daily_follow, _ = database.get_today_stats()
                    logger.info(f"{Fore.GREEN}✅ Follow: @{username} [{daily_follow}/{config.DAILY_FOLLOW_LIMIT}]")
                    
                    # Backup (har 5 ta)
                    if daily_follow % 5 == 0:
                        try:
                            import backup
                            cookies = self.context.cookies() # Eng yangi cookielar
                            backup.backup_cookies_to_gist(cookies)
                            # backup.backup_to_gist() # DB backup shart emas, cookie muhimroq
                        except Exception as e:
                            logger.warning(f"⚠️ Backup xatosi: {e}")
                    
                    return True
                else:
                    return False
                
            except Exception as e:
                if "Target page, context or browser has been closed" in str(e):
                    raise e
                logger.error(f"❌ Xato @{username}: {e}")
                # Retry davom etadi
                
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
                                # CRITICAL: Har bir followerni bazaga "muhrlash"
                                database.register_follower(username)
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
                    # Agar o'zgarish bo'lmasa - kutib ko'rish
                    time.sleep(2)
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

    def get_my_following(self) -> set:
        """O'z followinglarimizni olish"""
        logger.info("📊 O'z followinglarimiz tekshirilmoqda...")
        try:
            # O'z profilga o'tish
            self.page.goto(f"https://www.instagram.com/{config.INSTAGRAM_USERNAME}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
            # Following tugmasini bosish
            try:
                following_link = self.page.locator('a[href$="/following/"]').first
                following_link.click()
                time.sleep(3)
            except:
                logger.error("❌ Following tugmasi topilmadi")
                return set()
            
            following = set()
            scroll_count = 0
            
            # Scroll loop
            while scroll_count < 30: # Max 30 scroll (ko'proq odam)
                user_links = self.page.locator('div[role="dialog"] a[href^="/"][role="link"]')
                
                # Agar user_links topilmasa variant 2
                if user_links.count() == 0:
                     user_links = self.page.locator('div[role="dialog"] span > a[href^="/"]')
                
                for i in range(user_links.count()):
                    try:
                        href = user_links.nth(i).get_attribute("href")
                        if href and href != "/":
                            username = href.strip("/").split("/")[-1] # faqat username
                            if username != config.INSTAGRAM_USERNAME:
                                following.add(username)
                    except:
                        pass
                
                # Scroll
                try:
                    dialog = self.page.locator('div[role="dialog"] div[style*="height"]')
                    if dialog.count() == 0:
                         # Alternativ dialog qidirish
                         dialog = self.page.locator('div[role="dialog"] > div > div > div:nth-child(3)')
                    
                    dialog.first.evaluate("node => node.scrollTop = node.scrollHeight")
                    time.sleep(1.5)
                except:
                    # Alternativ scroll
                    self.page.mouse.wheel(0, 1000)
                    time.sleep(1.5)
                
                logger.info(f"📊 Following progress: {len(following)} ta...")
                scroll_count += 1
                
                # Check end of list
                # (Murakkab logika shart emas, 30 scroll yetarli)
                
            return following
            
        except Exception as e:
            logger.error(f"❌ Following yig'ish xatosi: {e}")
            return set()

    def smart_cleanup_interactive(self):
        """
        SMART CLEANUP - Real-time GraphQL API orqali:
        1. O'z followerlarimni olish (kim meni follow qiladi)
        2. O'z followinglarimni olish (men kimlarni follow qilaman)
        3. Solishtirish: Men follow qilgan odam meni follow qiladimi?
        4. Agar YO'Q → UNFOLLOW
        """
        logger.info(f"\n{Fore.YELLOW}{'='*50}")
        logger.info("🧹 SMART CLEANUP (REAL-TIME GraphQL API)")
        logger.info(f"{'='*50}{Style.RESET_ALL}")
        
        try:
            # 1. O'z User ID ni olish
            my_user_id = self._get_my_user_id()
            if not my_user_id:
                logger.error("❌ User ID olinmadi!")
                return
            
            logger.info(f"✅ Mening User ID: {my_user_id}")
            
            # 2. Real-time FOLLOWERS olish (kim meni follow qiladi)
            logger.info("📥 Real-time followerlar olinmoqda...")
            my_followers = set(self._fetch_followers_api(my_user_id, max_count=2000))
            logger.info(f"✅ {len(my_followers)} ta follower topildi")
            
            # 3. Real-time FOLLOWING olish (men kimlarni follow qilaman)
            logger.info("📥 Real-time following olinmoqda...")
            my_following = self._fetch_following_api(my_user_id, max_count=2000)
            logger.info(f"✅ {len(my_following)} ta following topildi")
            
            # 4. Solishtirish - kim follow qaytarmagan?
            non_followers = [u for u in my_following if u not in my_followers]
            logger.info(f"❌ Follow qaytarmaganlar: {len(non_followers)} ta")
            
            if not non_followers:
                logger.info("✅ Barcha following sizni follow qiladi. Cleanup kerak emas!")
                return
            
            # 5. Unfollow qilish
            unfollow_count = 0
            limit = 80
            
            for i, username in enumerate(non_followers):
                if database.get_config("current_cycle", "auto") != 'cleanup':
                    logger.info("⚡ Cleanup to'xtatildi (yangi buyruq)")
                    break
                
                if unfollow_count >= limit:
                    logger.info("🛑 Unfollow limitga yetildi.")
                    break
                
                try:
                    logger.info(f"❌ [{i+1}/{len(non_followers)}] Unfollow: @{username}")
                    
                    # Profilga o'tish
                    self.page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=30000)
                    time.sleep(random.uniform(2, 4))
                    
                    # Following tugmasini topish
                    following_btn = self.page.locator('button:has-text("Following")').first
                    if not following_btn.is_visible():
                        following_btn = self.page.locator('button:has-text("Requested")').first
                    
                    if following_btn.is_visible():
                        following_btn.click()
                        time.sleep(1)
                        
                        unfollow_confirm = self.page.locator('button:has-text("Unfollow")').first
                        if unfollow_confirm.is_visible():
                            unfollow_confirm.click()
                            time.sleep(2)
                            
                            logger.info(f"✅ Unfollowed: @{username}")
                            database.update_status(username, 'unfollowed')
                            unfollow_count += 1
                            
                            if unfollow_count % 5 == 0:
                                try:
                                    import backup
                                    backup.backup_cookies_to_gist(self.context.cookies())
                                except:
                                    pass
                            
                            time.sleep(random.uniform(5, 10))
                    else:
                        logger.warning(f"⚠️ Following tugmasi topilmadi: @{username}")
                
                except Exception as e:
                    logger.error(f"❌ Xato @{username}: {e}")
            
            logger.info(f"\n{'='*50}")
            logger.info(f"🧹 CLEANUP TUGADI")
            logger.info(f"📊 Followerlar: {len(my_followers)} ta")
            logger.info(f"📊 Following: {len(my_following)} ta")
            logger.info(f"❌ Non-followers: {len(non_followers)} ta")
            logger.info(f"✅ Unfollowed: {unfollow_count} ta")
            logger.info(f"{'='*50}")
            
        except Exception as e:
            logger.error(f"❌ Cleanup xatosi: {e}")
    
    def _fetch_following_api(self, user_id: str, max_count: int = 1000) -> list:
        """Instagram GraphQL API orqali FOLLOWING olish (men kimlarni follow qilaman)"""
        following = []
        end_cursor = ""
        page_count = 0
        
        try:
            while len(following) < max_count and page_count < 50:
                import urllib.parse
                import json
                
                variables = {"id": user_id, "first": 50}
                if end_cursor:
                    variables["after"] = end_cursor
                
                # FOLLOWING uchun boshqa query hash
                query_hash = "d04b0a864b4b54837c0d870b0e77e076"  # edge_follow query
                url = f"https://www.instagram.com/graphql/query/?query_hash={query_hash}&variables={urllib.parse.quote(json.dumps(variables))}"
                
                result = self.page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch("{url}", {{
                            headers: {{ "x-requested-with": "XMLHttpRequest" }},
                            credentials: "include"
                        }});
                        return await resp.json();
                    }} catch(e) {{
                        return null;
                    }}
                }}""")
                
                if not result or 'data' not in result:
                    logger.warning("⚠️ Following API javob yo'q")
                    break
                
                edges = result.get('data', {}).get('user', {}).get('edge_follow', {}).get('edges', [])
                
                if not edges:
                    break
                
                for edge in edges:
                    username = edge.get('node', {}).get('username')
                    if username:
                        following.append(username)
                
                page_info = result.get('data', {}).get('user', {}).get('edge_follow', {}).get('page_info', {})
                has_next = page_info.get('has_next_page', False)
                end_cursor = page_info.get('end_cursor', '')
                
                page_count += 1
                logger.info(f"📊 Following API: {len(following)} ta ({page_count} sahifa)")
                
                if not has_next:
                    break
                
                time.sleep(1)
            
            return following
            
        except Exception as e:
            logger.error(f"❌ Following API xatosi: {e}")
            return []
    
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
        
        # Blocked bo'lmaganlarni olish (fail_count < 3)
        waiting_users = database.get_waiting_users_for_unfollow(50)
        if not waiting_users:
            logger.info("✅ Tekshiradiganlar yo'q")
            return

        # BAZADAN followerlarni olish (UI emas!)
        my_followers = database.get_followers_from_db()
        logger.info(f"📊 Bazadan {len(my_followers)} ta follower topildi")
        
        now = datetime.now()
        to_unfollow = []
        
        for user in waiting_users:
            if not user.get('followed_at'):
                continue
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
            
            # 24 soatlik himoya va Status tekshiruvi w
            user_data = database.get_user(username)
            if user_data:
                user_data = dict(user_data) # Fix: sqlite3.Row -> dict conversion
                
                # 1. Agar statusi 'followed_back' bo'lsa
                if user_data.get('status') == 'followed_back':
                     logger.info(f"⏭️ @{username} o'tkazib yuborildi (Status: followed_back)")
                     continue
                
                # 2. 24 soatlik himoya (FAQAT GENTLE MODE UCHUN)
                strict_mode = database.get_config("strict_mode", "false") == "true"
                if not strict_mode and user_data.get('followed_at'):
                    try:
                        followed_at = datetime.fromisoformat(user_data['followed_at'])
                        hours_diff = (datetime.now() - followed_at).total_seconds() / 3600
                        if hours_diff < 24:
                            logger.info(f"⏭️ @{username} o'tkazib yuborildi (Hali 24 soat bo'lmadi: {hours_diff:.1f}s)")
                            time.sleep(0.1)
                            continue
                    except:
                        pass

            try:
                if self.unfollow_user(username):
                    unfollowed += 1
                    result["unfollowed"] += 1
                    
                    delay = self.get_human_delay(config.UNFOLLOW_DELAY_MIN, config.UNFOLLOW_DELAY_MAX)
                    logger.info(f"⏳ {delay} sekund kutilmoqda...")
                    
                    # Smart sleep (Buyruq o'zgarsa)
                    if self.smart_sleep(delay):
                        break
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
                self.page.goto(f"https://www.instagram.com/{username}/", wait_until="commit", timeout=15000)
                time.sleep(2)
                
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
                logger.warning(f"⚠️ Profil yuklanmadi @{username}: {e}")
                # Fail count ni oshirish va skip qilish
                fail_count = database.increment_fail_count(username)
                if fail_count >= 3:
                    database.mark_as_blocked(username)
                return False

            logger.info(f"🔍 User ID qidirilmoqda: @{username}")
            # 2. User ID ni olish (JavaScript orqali)
            user_id = None
            try:
                # Method 1: API orqali (Eng ishonchli)
                profile_json_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
                user_info = self.page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch("{profile_json_url}", {{
                            headers: {{ 
                                "X-IG-App-ID": "936619743392459",
                                "X-Requested-With": "XMLHttpRequest"
                            }}
                        }});
                        const data = await resp.json();
                        return {{
                            id: data.data?.user?.id,
                            follows_viewer: data.data?.user?.follows_viewer,
                            status: data.status,
                            error: data.message
                        }};
                    }} catch(e) {{ return {{ error: e.toString() }}; }}
                }}""")
                
                logger.info(f"📨 API Response @{username}: {user_info}")
                
                if user_info and user_info.get('id'):
                    user_id = user_info['id']
                    
                    # ⚠️ CRITICAL: Agar u bizga follow qilgan bo'lsa - UNFOLLOW QILMAYMIZ!
                    if user_info.get('follows_viewer') is True:
                         logger.warning(f"🛑 @{username} sizga follow qilgan! (Unfollow bekor qilindi)")
                         database.update_status(username, 'followed_back')
                         return False
                elif user_info and user_info.get('error'):
                    # API xatosi - ehtimol profil mavjud emas
                    logger.warning(f"⚠️ @{username} - API xatosi: {user_info.get('error')}")
                
                # Method 2: Meta taglardan (Fallback - 5s timeout)
                if not user_id:
                    try:
                        user_id = self.page.locator('meta[property="instapp:owner_user_id"]').get_attribute('content', timeout=5000)
                    except:
                        pass
            except Exception as e:
                logger.warning(f"⚠️ User ID olishda xato: {e}")
            
            # Agar user_id topilmasa - skip qilish!
            if not user_id:
                logger.warning(f"⚠️ @{username} uchun User ID topilmadi. Skip qilinmoqda...")
                fail_count = database.increment_fail_count(username)
                if fail_count >= 3:
                    database.mark_as_blocked(username)
                return False
            
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
                        # CRITICAL FIX: 30 sekund timeout qo'shildi (hang oldini olish)
                        self.page.reload(timeout=30000)
                        time.sleep(3)
                        
                        # Buttonni kengroq qidirish (nafaqat header ichida)
                        follow_btn = self.page.locator('button').filter(has_text=re.compile(r"Follow|Obuna bo'lish|Подписаться|Takip et", re.IGNORECASE)).first
                        
                        if follow_btn.is_visible(timeout=5000):
                            database.update_status(username, 'unfollowed')
                            _, daily_unfollow = database.get_today_stats()
                            logger.info(f"{Fore.RED}🚫 Unfollow TASDIQLANDI: @{username} [{daily_unfollow}/{config.DAILY_UNFOLLOW_LIMIT}]")
                            return True
                        else:
                            # Balki hali ham "Following" tur gandir?
                            following_check = self.page.locator('button').filter(has_text=re.compile(r"Following|Requested|Obuna bo'lingan", re.IGNORECASE)).first
                            if following_check.is_visible(timeout=5000):
                                logger.warning(f"⚠️ API 'ok' dedi, lekin hali ham 'Following' turibdi @{username}")
                            else:
                                logger.warning(f"⚠️ Sahifada na Follow, na Following tugmasi topildi @{username}")
                    except Exception as verify_error:
                         logger.warning(f"⚠️ Verifikatsiya xatosi (30s timeout?): {verify_error}")
                         # Agar reload xato bersa ham, API muvaffaqiyatli bo'lgan - statusni yangilaymiz
                         database.update_status(username, 'unfollowed')
                         _, daily_unfollow = database.get_today_stats()
                         logger.info(f"{Fore.YELLOW}🚫 Unfollow (API orqali, UI tasdiqsiz): @{username} [{daily_unfollow}/{config.DAILY_UNFOLLOW_LIMIT}]")
                         return True

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
            
            # Fail count ni oshirish va 3 dan oshsa blocked deb belgilash
            fail_count = database.increment_fail_count(username)
            if fail_count >= 3:
                database.mark_as_blocked(username)
            
            return False
    
    def watch_stories_and_like(self, duration: int, wait_remaining: bool = True):
        """
        Storylarni tomosha qilish va like bosish (Human-Like Behavior)
        Sleep o'rniga ishlatiladi.
        
        Args:
            duration: Maksimal vaqt (sekund)
            wait_remaining: True bo'lsa qolgan vaqtni kutadi, False bo'lsa darhol qaytadi
        """
        import re
        # Boshlang'ich siklni eslab qolamiz (agar o'zgarsa, loopni buzish uchun)
        initial_cycle = database.get_config("current_cycle", "auto")
        logger.info(f"🍿 Story tomosha qilish rejimi: {duration} sekund... (Mode: {initial_cycle})")
        
        start_time = time.time()
        
        # IMMEDIATE CHECK: Agar buyruq allaqachon o'zgargan bo'lsa, hech narsa qilmaymiz
        current_check = database.get_config("current_cycle", "auto")
        if current_check != initial_cycle and current_check != "auto":
            logger.info(f"⚡ Story o'tkazib yuborildi (Yangi buyruq: {current_check})")
            return
        
        try:
            # 1. Bosh sahifaga o'tish
            if self.page.url != "https://www.instagram.com/":
                try:
                    self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
                except Exception as goto_err:
                     logger.warning(f"⚠️ Main page fetch warning: {goto_err}")
                     # Agar url ochilgan bo'lsa davom etaveramiz
                     if "instagram.com" not in self.page.url: raise goto_err
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
            same_user_count = 0  # Bir xil user takrorlanish hisoblagichi
            last_user = None  # Oldingi ko'rilgan user
            
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

                # STUCK DETECTION: Agar bir xil user 5+ marta ko'rinsa, story qotib qolgan
                if current_username == last_user:
                    same_user_count += 1
                    if same_user_count >= 5:
                        logger.warning(f"⚠️ Story qotib qoldi ({current_username} 5+ marta). Chiqilmoqda...")
                        # Sahifani yangilab, qotib qolishdan chiqish
                        self.refresh_page_if_stuck()
                        break
                else:
                    same_user_count = 0
                    last_user = current_username

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
                if current_cycle_check != initial_cycle:
                     logger.info(f"⚡ Story ko'rish to'xtatildi (Yangi buyruq: {current_cycle_check})")
                     break

                time.sleep(watch_time)
                
                # Random Like (100% ehtimol - Test uchun)
                if random.random() < 1.0:
                    try:
                        # 1. AVVAL TEKSHIRAMIZ: Allaqaqchon like bosilganmi?
                        # Unlike tugmasini qidirish (Barchasini tekshiramiz)
                        unlike_selector = (
                            'svg[aria-label*="Unlike"], '
                            'svg[aria-label*="O\'chirish"], '
                            'svg[aria-label*="Yoqtirishni bekor qilish"], '
                            'svg[aria-label*="Vazgeç"], '
                            'svg[aria-label*="Je n\'aime plus"]'
                        )
                        
                        unlike_svgs = self.page.locator(unlike_selector)
                        is_liked = False
                        clicked = False  # To prevent UnboundLocalError
                        
                        # Barcha unlike tugmalarini tekshiramiz (qaysidir biri ko'rinib turgandir)
                        for i in range(unlike_svgs.count()):
                            if unlike_svgs.nth(i).is_visible():
                                is_liked = True
                                break
                        
                        if is_liked:
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
                                    try:
                                        # Parent (Button) ni olish
                                        like_btn = svg.locator("..")
                                        like_btn.click(force=True)
                                        clicked = True
                                        logger.info(f"{Fore.MAGENTA}❤️ Storyga Like bosildi!")
                                        
                                        # Link yasash (Xatolikni oldini olish uchun)
                                        if "Noma'lum" in current_username:
                                            user_display = f"<i>{current_username}</i>"
                                        else:
                                            user_display = f"<a href='https://instagram.com/{current_username}'>@{current_username}</a>"
                                            
                                        self.send_telegram_msg(f"❤️ <b>Storyga Like bosildi:</b> {user_display}")
                                        time.sleep(1)
                                        break
                                    except Exception as click_err:
                                        logger.warning(f"⚠️ Like tugmasini bosishda muammo (keyingisini ko'ramiz): {click_err}")
                                        continue
                        
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
            
        # Agar vaqt ortib qolsa va wait_remaining=True bo'lsa - kutish
        if not wait_remaining:
            logger.info("✅ Storylar tugadi. Darhol davom etilmoqda.")
            return
            
        remaining = duration - (time.time() - start_time)
        # MAX 1 soat kutish (uzun hang ni oldini olish)
        remaining = min(remaining, 3600)
        
        if remaining > 0:
            logger.info(f"⏳ Qolgan vaqt: {int(remaining)}s. (Buyruqlar kutilmoqda...)")
            
            slept = 0
            while slept < remaining:
                time.sleep(1)
                slept += 1
                
                # Buyruqni tekshirish
                current_cycle_check = database.get_config("current_cycle", "auto")
                if current_cycle_check != initial_cycle:
                     logger.info(f"⚡ Kutish to'xtatildi (Yangi buyruq: {current_cycle_check})")
                     break
            
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
    
    def sync_my_followers(self):
        """Startup: Barcha followerlarni bazaga muhrlash (GraphQL API orqali)"""
        logger.info(f"\n{'='*50}")
        logger.info("🔄 STARTUP SYNC: GraphQL API orqali followerlar olinmoqda...")
        logger.info(f"{'='*50}\n")
        
        try:
            # 1. User ID olish
            user_id = self._get_my_user_id()
            if not user_id:
                logger.warning("⚠️ User ID olinmadi, UI scroll ga o'tilmoqda...")
                self._sync_followers_ui_fallback()
                return
            
            logger.info(f"✅ User ID: {user_id}")
            
            # 2. GraphQL API orqali followers olish
            followers = self._fetch_followers_api(user_id)
            
            if followers:
                followers_set = set(followers)
                logger.info(f"📥 API dan {len(followers_set)} ta follower olindi")
                
                # 3. Yangi followerlarni bazaga qo'shish
                for username in followers_set:
                    database.register_follower(username)
                
                # 4. MUHIM: Eski followerlarni tozalash
                # Bazadagi followed_back larni olish
                old_followers = database.get_followers_from_db()
                lost_count = 0
                
                for old_user in old_followers:
                    if old_user not in followers_set:
                        # Bu user endi follower emas - statusni o'zgartirish
                        database.update_status(old_user, 'lost_follower')
                        lost_count += 1
                
                if lost_count > 0:
                    logger.info(f"🔄 {lost_count} ta eski follower 'lost_follower' ga o'zgartirildi")
                
                logger.info(f"✅ SYNC TUGADI: Jami {len(followers_set)} ta haqiqiy follower bazada.")
            else:
                logger.warning("⚠️ API dan follower olinmadi, UI fallback...")
                self._sync_followers_ui_fallback()
                
        except Exception as e:
            logger.error(f"❌ Sync xatosi: {e}")
            self._sync_followers_ui_fallback()
    
    def _get_my_user_id(self):
        """O'z user ID ni olish"""
        try:
            self.page.goto(f"https://www.instagram.com/{config.INSTAGRAM_USERNAME}/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # HTML source dan user_id ni ajratib olish
            user_id = self.page.evaluate("""() => {
                const html = document.documentElement.innerHTML;
                
                // Usul 1: profilePage_XXXXX
                let match = html.match(/"profilePage_([0-9]+)"/);
                if (match) return match[1];
                
                // Usul 2: user_id":"XXXXX
                match = html.match(/"user_id":"([0-9]+)"/);
                if (match) return match[1];
                
                // Usul 3: logging_page_id dari
                match = html.match(/"logging_page_id":"profilePage_([0-9]+)"/);
                if (match) return match[1];
                
                return null;
            }""")
            
            return user_id
        except Exception as e:
            logger.error(f"❌ User ID olishda xato: {e}")
            return None
    
    def _fetch_followers_api(self, user_id, max_count=1000):
        """Instagram GraphQL API orqali followers olish"""
        followers = []
        end_cursor = ""
        page_count = 0
        
        try:
            while len(followers) < max_count and page_count < 50:
                # GraphQL query yasash
                import urllib.parse
                import json
                
                variables = {"id": user_id, "first": 50}
                if end_cursor:
                    variables["after"] = end_cursor
                
                # Query hash - Instagram followers uchun
                query_hash = "c76146de99bb02f6415203be841dd25a"
                url = f"https://www.instagram.com/graphql/query/?query_hash={query_hash}&variables={urllib.parse.quote(json.dumps(variables))}"
                
                # Fetch qilish (browser context orqali - cookies avtomatik)
                result = self.page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch("{url}", {{
                            headers: {{
                                "x-requested-with": "XMLHttpRequest"
                            }},
                            credentials: "include"
                        }});
                        return await resp.json();
                    }} catch(e) {{
                        return null;
                    }}
                }}""")
                
                if not result or 'data' not in result:
                    logger.warning(f"⚠️ GraphQL javob yo'q yoki xato")
                    break
                
                edges = result.get('data', {}).get('user', {}).get('edge_followed_by', {}).get('edges', [])
                
                if not edges:
                    logger.info("📭 Boshqa follower yo'q")
                    break
                
                for edge in edges:
                    username = edge.get('node', {}).get('username')
                    if username:
                        followers.append(username)
                
                # Keyingi sahifa
                page_info = result.get('data', {}).get('user', {}).get('edge_followed_by', {}).get('page_info', {})
                has_next = page_info.get('has_next_page', False)
                end_cursor = page_info.get('end_cursor', '')
                
                page_count += 1
                logger.info(f"📊 API Progress: {len(followers)} ta follower ({page_count} sahifa)")
                
                if not has_next:
                    break
                    
                time.sleep(1)  # Rate limit
            
            return followers
            
        except Exception as e:
            logger.error(f"❌ GraphQL API xatosi: {e}")
            return []
    
    def _sync_followers_ui_fallback(self):
        """UI Scroll fallback (API ishlamasa)"""
        logger.info("🔄 UI Scroll fallback ishga tushdi...")
        
        try:
            self.page.goto(f"https://www.instagram.com/{config.INSTAGRAM_USERNAME}/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
            followers_link = self.page.locator('a[href$="/followers/"]').first
            followers_link.click()
            time.sleep(5)
            
            collected = set()
            scroll_count = 0
            retry = 0
            
            IGNORE = {'explore', 'reels', 'stories', 'direct', 'accounts', config.INSTAGRAM_USERNAME, 'create', 'guide'}
            
            while scroll_count < 100 and retry < 5:
                links = self.page.locator('div[role="dialog"] a[href^="/"]')
                count = links.count()
                prev_len = len(collected)
                
                for i in range(count):
                    try:
                        href = links.nth(i).get_attribute("href")
                        if href and href.startswith("/"):
                            u = href.strip("/").split("/")[0]
                            if u and len(u) >= 2 and u not in IGNORE and u not in collected:
                                collected.add(u)
                                database.register_follower(u)
                    except:
                        pass
                
                if len(collected) == prev_len:
                    retry += 1
                    time.sleep(3)
                else:
                    retry = 0
                
                # Scroll
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
                time.sleep(2)
                scroll_count += 1
                
                if scroll_count % 5 == 0:
                    logger.info(f"📊 UI Progress: {len(collected)} ta topildi...")
            
            self.page.keyboard.press("Escape")
            logger.info(f"✅ UI Fallback: {len(collected)} ta follower topildi")
            
        except Exception as e:
            logger.error(f"❌ UI Fallback xatosi: {e}")

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
        
        # CRITICAL: Server startda har doim bazani yangilaymiz!
        bot.sync_my_followers()
        
        # IMPORTANT: Startup rejimda "auto" holatiga qaytaramiz
        database.set_config("current_cycle", "auto")
        database.set_config("strict_mode", "false")
        
        # Har soatlik sync uchun vaqtni eslab qolamiz
        last_sync_time = datetime.now()
        
        try:
            while True:
                try:
                    # 🔄 HAR SOATLIK SYNC: Yangi followerlarni tekshirish
                    hours_since_sync = (datetime.now() - last_sync_time).total_seconds() / 3600
                    if hours_since_sync >= 1:
                        logger.info("🔄 Har soatlik sync: Yangi followerlar tekshirilmoqda...")
                        bot.sync_my_followers()
                        last_sync_time = datetime.now()
                    
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
                        
                        bot.smart_cleanup_interactive()
                        
                        logger.info("✅ Cleanup tugadi. Auto rejimga qaytilmoqda.")
                        database.set_config("current_cycle", "auto")

                    # ------------------------------------------
                    # MODE 3: STORIES (Faqat Story ko'rish)
                    # ------------------------------------------
                    elif current_cycle == 'stories':
                        logger.info(f"\n{'='*40}")
                        logger.info("🍿 STORY MODE BOSHLANDI")
                        logger.info(f"{'='*40}")
                        
                        # Storylarni ko'rish (tugagandan keyin KUTMASDAN davom etadi)
                        bot.watch_stories_and_like(3600, wait_remaining=False)  # Tugagach darhol qaytadi
                        
                        logger.info("✅ Story ko'rish tugadi. Darhol auto rejimga qaytilmoqda.")
                        database.set_config("current_cycle", "auto")

                    # ------------------------------------------
                    # MODE 4: FOLLOW (Direct Follow)
                    # ------------------------------------------
                    elif current_cycle == 'follow':
                        target = database.get_config("follow_target")
                        count = int(database.get_config("follow_count", "20"))
                        
                        logger.info(f"\n{'='*40}")
                        logger.info(f"🚀 FOLLOW CYCLE BOSHLANDI: @{target} ({count} ta)")
                        logger.info(f"{'='*40}")
                        
                        bot.run_follow_cycle(count, target)
                        
                        logger.info("✅ Follow sikli tugadi. Auto rejimga qaytilmoqda.")
                        database.set_config("current_cycle", "auto")

                    # ------------------------------------------
                    # MODE 3: AUTO (Faqat Baza bilan ishlash)
                    # ------------------------------------------
                    else:
                        # 1. Follow (FAQAT Pending userlar)
                        pending_count = database.get_pending_count()
                        
                        # LIMIT TEKSHIRISH (Spam oldini olish)
                        daily_follow, _ = database.get_today_stats()
                        if daily_follow >= config.DAILY_FOLLOW_LIMIT:
                            logger.info(f"💤 Kunlik follow limiti tugadi ({daily_follow}/{config.DAILY_FOLLOW_LIMIT}). Keyingi kunga kutamiz.")
                        elif pending_count > 0:
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
                            # ⚠️ FALLBACK: Pending bo'sh - random targetdan follow qilish
                            random_target = database.get_random_target()
                            if random_target:
                                logger.info(f"🎲 Pending bo'sh. Random target tanlandi: @{random_target}")
                                bot.run_follow_cycle(20, random_target)
                            else:
                                logger.info("💤 Baza bo'sh va target yo'q. /add_target yoki /collect buyrug'ini ishlating.")
                            
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
                    logger.info(f"⏳ Sikl tugadi. {wait_time/60:.1f} daqiqa davomida Story ko'riladi (Smart Sleep)...")
                    
                    # Sleep o'rniga Story ko'rish (ichida buyruqni tekshiradi)
                    bot.watch_stories_and_like(wait_time)
                            
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

