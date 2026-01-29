"""
Instagram Bot - Follower Sync
Follower sinxronizatsiya funksiyalari
"""

import time
import logging
from colorama import Fore

import config
import database
from .api import InstagramAPI

logger = logging.getLogger(__name__)


class InstagramSync:
    """Follower/Following sinxronizatsiya"""
    
    def __init__(self, page, context=None):
        self.page = page
        self.context = context
        self.api = InstagramAPI(page, context)
    
    def sync_my_followers(self):
        """Startup: Barcha followerlarni bazaga muhrlash (GraphQL API orqali)"""
        logger.info(f"\n{'='*50}")
        logger.info("🔄 STARTUP SYNC: GraphQL API orqali followerlar olinmoqda...")
        logger.info(f"{'='*50}\n")
        
        try:
            # 1. User ID olish
            user_id = self.api.get_my_user_id()
            if not user_id:
                logger.warning("⚠️ User ID olinmadi, UI scroll ga o'tilmoqda...")
                self._sync_followers_ui_fallback()
                return
            
            logger.info(f"✅ User ID: {user_id}")
            
            # 2. GraphQL API orqali followers olish
            followers = self.api.fetch_followers_api(user_id)
            
            if followers:
                followers_set = set(followers)
                logger.info(f"📥 API dan {len(followers_set)} ta follower olindi")
                
                # 3. Yangi followerlarni bazaga qo'shish
                for username in followers_set:
                    database.register_follower(username)
                
                # 4. Eski followerlarni tozalash
                old_followers = database.get_followers_from_db()
                lost_count = 0
                
                for old_user in old_followers:
                    if old_user not in followers_set:
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
    
    def _sync_followers_ui_fallback(self):
        """UI Scroll fallback (API ishlamasa)"""
        logger.info("🔄 UI Scroll fallback ishga tushdi...")
        
        try:
            self.page.goto(f"https://www.instagram.com/{config.INSTAGRAM_USERNAME}/", 
                          wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
            followers_link = self.page.locator('a[href$="/followers/"]').first
            followers_link.click()
            time.sleep(5)
            
            collected = set()
            scroll_count = 0
            retry = 0
            
            IGNORE = {'explore', 'reels', 'stories', 'direct', 'accounts', 
                     config.INSTAGRAM_USERNAME, 'create', 'guide'}
            
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
    
    def get_my_followers_ui(self) -> set:
        """O'z followerlarimizni UI orqali olish"""
        logger.info("📊 O'z followerlarimiz tekshirilmoqda...")
        try:
            self.page.goto(f"https://www.instagram.com/{config.INSTAGRAM_USERNAME}/", 
                          wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
            followers_link = self.page.locator('a[href$="/followers/"]').first
            followers_link.click()
            time.sleep(3)
            
            followers = set()
            scroll_count = 0
            prev_count = 0
            
            while scroll_count < 20:
                follower_links = self.page.locator('div[role="dialog"] a[href^="/"]')
                
                for i in range(follower_links.count()):
                    try:
                        href = follower_links.nth(i).get_attribute("href")
                        if href and href.startswith("/"):
                            username = href.strip("/").split("/")[0]
                            if username:
                                followers.add(username)
                                database.register_follower(username)
                    except:
                        continue
                
                try:
                    self.page.mouse.wheel(0, 3000)
                    time.sleep(1)
                except:
                    pass
                
                scroll_count += 1
                if len(followers) == prev_count:
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

    def get_my_following_ui(self) -> set:
        """O'z followinglarimizni UI orqali olish"""
        logger.info("📊 O'z followinglarimiz tekshirilmoqda...")
        try:
            self.page.goto(f"https://www.instagram.com/{config.INSTAGRAM_USERNAME}/", 
                          wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
            try:
                following_link = self.page.locator('a[href$="/following/"]').first
                following_link.click()
                time.sleep(3)
            except:
                logger.error("❌ Following tugmasi topilmadi")
                return set()
            
            following = set()
            scroll_count = 0
            
            while scroll_count < 30:
                user_links = self.page.locator('div[role="dialog"] a[href^="/"][role="link"]')
                
                if user_links.count() == 0:
                    user_links = self.page.locator('div[role="dialog"] span > a[href^="/"]')
                
                for i in range(user_links.count()):
                    try:
                        href = user_links.nth(i).get_attribute("href")
                        if href and href != "/":
                            username = href.strip("/").split("/")[-1]
                            if username != config.INSTAGRAM_USERNAME:
                                following.add(username)
                    except:
                        pass
                
                try:
                    dialog = self.page.locator('div[role="dialog"] div[style*="height"]')
                    if dialog.count() == 0:
                        dialog = self.page.locator('div[role="dialog"] > div > div > div:nth-child(3)')
                    dialog.first.evaluate("node => node.scrollTop = node.scrollHeight")
                    time.sleep(1.5)
                except:
                    self.page.mouse.wheel(0, 1000)
                    time.sleep(1.5)
                
                logger.info(f"📊 Following progress: {len(following)} ta...")
                scroll_count += 1
                
            return following
            
        except Exception as e:
            logger.error(f"❌ Following yig'ish xatosi: {e}")
            return set()

    def collect_followers(self, target: str, max_count: int = 1000) -> dict:
        """Target followerlarini bazaga to'plash (GraphQL API orqali)"""
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
            target_user_id = self.api.get_target_user_id(target)
            
            if not target_user_id:
                logger.warning("⚠️ Target User ID olinmadi, UI scroll ga o'tilmoqda...")
                return self._collect_followers_ui_fallback(target, max_count)
            
            logger.info(f"✅ Target User ID: {target_user_id}")
            
            # 2. GraphQL API orqali followers olish
            followers = self.api.fetch_followers_api(target_user_id, max_count)
            
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
    
    def _collect_followers_ui_fallback(self, target: str, max_count: int) -> dict:
        """UI Scroll fallback (API ishlamasa)"""
        logger.info("🔄 UI Scroll fallback ishga tushdi...")
        
        result = {"target": target, "total_found": 0, "new_added": 0, "already_in_db": 0, "errors": 0}
        
        try:
            self.page.goto(f"https://www.instagram.com/{target}/", 
                          wait_until="domcontentloaded", timeout=60000)
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
            IGNORE = {'explore', 'reels', 'stories', 'direct', 'accounts', 
                     config.INSTAGRAM_USERNAME, 'create', 'guide', target}
            
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

    def get_followers_of_target(self, count: int = 30, target: str = None) -> list:
        """Target akkauntning followerlarini olish"""
        if target is None:
            target = config.TARGET_ACCOUNT
        
        logger.info(f"🎯 @{target} followerlarini olmoqda...")
        
        try:
            self.page.goto(f"https://www.instagram.com/{target}/", 
                          wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            
            followers_link = self.page.locator('a[href$="/followers/"]').first
            followers_link.click()
            time.sleep(5)
            
            dialog = self.page.locator('div[role="dialog"]').first
            dialog.wait_for(timeout=30000)
            time.sleep(5)
            
            for _ in range(3):
                self.page.keyboard.press("PageDown")
                time.sleep(0.5)
            time.sleep(3)
            
            users = []
            scroll_count = 0
            MAX_SCROLLS = 100
            
            logger.info("🔍 Deep Scroll boshlandi...")
            
            seen_usernames = set()
            
            while len(users) < count and scroll_count < MAX_SCROLLS:
                dialog = self.page.locator('div[role="dialog"]').first
                
                if scroll_count == 0:
                    time.sleep(3)
                
                follower_links = dialog.locator('a')
                current_batch_count = follower_links.count()
                
                if scroll_count == 0:
                    logger.info(f"📊 Dialog da {current_batch_count} ta link topildi")
                    if current_batch_count == 0:
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
                            
                        username = href.strip("/").split("/")[0]
                        
                        if not username or len(username) < 2:
                            skipped_invalid += 1
                            continue
                        if username == target or username in ['explore', 'reels', 'stories', 'direct', 'accounts']:
                            skipped_invalid += 1
                            continue
                        
                        if username in seen_usernames:
                            continue
                        seen_usernames.add(username)
                        
                        if database.get_user(username):
                            skipped_in_db += 1
                            continue
                            
                        users.append(username)
                        new_in_this_scroll += 1
                        
                    except Exception as e:
                        continue
                
                if skipped_in_db > 0 or skipped_invalid > 0:
                    logger.info(f"📊 Scroll #{scroll_count}: +{new_in_this_scroll} yangi, {skipped_in_db} bazada bor, {skipped_invalid} noto'g'ri")
                
                if len(users) >= count:
                    logger.info(f"✅ Yetarlicha yangi user topildi: {len(users)} ta")
                    break
                
                # Scroll
                try:
                    scroll_success = self.page.evaluate("""() => {
                        const dialog = document.querySelector('div[role="dialog"]');
                        if (!dialog) return false;
                        
                        const containers = dialog.querySelectorAll('div');
                        let scrolled = false;
                        
                        for (const div of containers) {
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
                        try:
                            dialog.click()
                            time.sleep(0.3)
                            for _ in range(3):
                                self.page.keyboard.press("PageDown")
                                time.sleep(0.2)
                        except:
                            pass
                    
                    if not scroll_success:
                        try:
                            box = dialog.bounding_box()
                            if box:
                                self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                                self.page.mouse.wheel(0, 1000)
                        except:
                            pass
                    
                    logger.info(f"🖱️ Scroll #{scroll_count}: {len(users)}/{count} yangi user topildi")
                    time.sleep(1.5)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Scroll xatosi: {e}")
                    time.sleep(1)
                
                scroll_count += 1
            
            self.page.keyboard.press("Escape")
            time.sleep(1)
            
            logger.info(f"✅ {len(users)} ta follower topildi")
            return users[:count]
            
        except Exception as e:
            logger.error(f"❌ Followers olishda xato: {e}")
            return []
