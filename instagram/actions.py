"""
Instagram Bot - Follow/Unfollow Actions
Follow va Unfollow amaliyotlari
"""

import re
import time
import random
import logging
from datetime import datetime
from colorama import Fore

import config
import database
from .api import InstagramAPI
from .utils import get_human_delay, update_heartbeat

logger = logging.getLogger(__name__)


class InstagramActions:
    """Follow/Unfollow amaliyotlari"""
    
    def __init__(self, page, context=None):
        self.page = page
        self.context = context
        self.api = InstagramAPI(page, context)
        self.consecutive_timeouts = 0
    
    def follow_user(self, username: str) -> bool:
        """Foydalanuvchini follow qilish (API + Retry va Timeout himoyasi bilan)"""
        
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
                # 5+ ketma-ket timeout bo'lsa, brauzerni yangilash
                if self.consecutive_timeouts >= 5:
                    logger.warning(f"⚠️ {self.consecutive_timeouts} ta ketma-ket timeout! Browser yangilanmoqda...")
                    self._refresh_page()
                    self.consecutive_timeouts = 0
                    time.sleep(3)
                
                # Random delay (Anti-Spam)
                time.sleep(random.uniform(1, 2))
                
                logger.info(f"🔍 Profilga kirilmoqda: @{username} (Urinish: {attempt+1}/{max_retries})")
                
                # Profilga o'tish (90s Timeout)
                try:
                    self.page.goto(f"https://www.instagram.com/{username}/", wait_until="commit", timeout=90000)
                    try:
                        self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except:
                        pass
                    self.consecutive_timeouts = 0
                except Exception as goto_err:
                    self.consecutive_timeouts += 1
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️ Timeout ({self.consecutive_timeouts}). 2s kutib qayta urinamiz...")
                        time.sleep(2)
                        continue
                    else:
                        logger.error(f"❌ Profil yuklanmadi @{username}: Timeout")
                        return False

                time.sleep(random.uniform(1, 2))
                
                # Follow tugmasini qidirish (5s timeout bilan)
                try:
                    follow_btn = self.page.locator('button:has-text("Follow")').first
                    follow_btn.wait_for(state="visible", timeout=5000)
                    follow_visible = True
                except:
                    follow_visible = False
                
                # Agar Follow tugmasi bo'lmasa
                if not follow_visible:
                    # Allaqachon follow qilinganmi?
                    already_followed = False
                    try:
                        combined_selector = 'button:has-text("Following"), button:has-text("Requested"), div:has-text("Message")'
                        self.page.locator(combined_selector).first.wait_for(state="visible", timeout=3000)
                        already_followed = True
                    except:
                        pass
                    
                    if already_followed:
                        logger.info(f"⏭️ @{username} allaqachon follow qilingan - statusni 'waiting' ga o'zgartiramiz")
                        database.update_status(username, 'waiting')
                        return False
                    
                    logger.warning(f"⚠️ @{username}: Follow tugmasi topilmadi. Skip.")
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
                            cookies = self.context.cookies()
                            backup.backup_cookies_to_gist(cookies)
                        except Exception as e:
                            logger.warning(f"⚠️ Backup xatosi: {e}")
                    
                    return True
                else:
                    return False
                
            except Exception as e:
                if "Target page, context or browser has been closed" in str(e):
                    raise e
                logger.error(f"❌ Xato @{username}: {e}")
                
        return False
    
    def unfollow_user(self, username: str) -> bool:
        """Foydalanuvchini unfollow qilish (API + UI Fallback)"""
        
        _, daily_unfollow = database.get_today_stats()
        if daily_unfollow >= config.DAILY_UNFOLLOW_LIMIT:
            logger.warning(f"⚠️ Kunlik unfollow limiti tugadi")
            return False

        try:
            logger.info(f"⏳ Profilga o'tilmoqda: @{username}")
            
            # 1. Profilga o'tish
            try:
                self.page.goto(f"https://www.instagram.com/{username}/", wait_until="commit", timeout=45000)
                time.sleep(2)
                
                # Tezkor tekshiruv: Balki allaqachon unfollow qilingandir?
                head_check = self.page.locator('header section').first
                if not head_check.is_visible(): 
                    head_check = self.page.locator('main header').first
                
                check_btn = head_check.locator('button').filter(
                    has_text=re.compile(r"Follow|Obuna bo'lish|Подписаться|Takip et", re.IGNORECASE)
                ).first
                
                if check_btn.is_visible():
                    logger.info(f"ℹ️ @{username} allaqachon unfollow qilingan (Follow tugmasi bor)")
                    database.update_status(username, 'unfollowed')
                    return False

            except Exception as e:
                logger.warning(f"⚠️ Profil yuklanmadi @{username}: {e}")
                fail_count = database.increment_fail_count(username)
                if fail_count >= 3:
                    database.mark_as_blocked(username)
                return False

            # 2. User ID ni olish va follows_viewer tekshirish
            logger.info(f"🔍 User ID qidirilmoqda: @{username}")
            user_info = self.api.get_user_info(username)
            
            logger.info(f"📨 API Response @{username}: {user_info}")
            
            user_id = None
            if user_info and user_info.get('id'):
                user_id = user_info['id']
                
                # CRITICAL: Agar u bizga follow qilgan bo'lsa - UNFOLLOW QILMAYMIZ!
                if user_info.get('follows_viewer') is True:
                    logger.warning(f"🛑 @{username} sizga follow qilgan! (Unfollow bekor qilindi)")
                    database.update_status(username, 'followed_back')
                    return False
            elif user_info and user_info.get('error'):
                logger.warning(f"⚠️ @{username} - API xatosi: {user_info.get('error')}")
            
            # Meta taglardan (Fallback)
            if not user_id:
                try:
                    user_id = self.page.locator('meta[property="instapp:owner_user_id"]').get_attribute('content', timeout=5000)
                except:
                    pass
            
            # Agar user_id topilmasa - skip
            if not user_id:
                logger.warning(f"⚠️ @{username} uchun User ID topilmadi. Skip qilinmoqda...")
                fail_count = database.increment_fail_count(username)
                if fail_count >= 3:
                    database.mark_as_blocked(username)
                return False
            
            # 3. API orqali Unfollow
            if user_id:
                logger.info(f"🔧 API Unfollow: @{username} (ID: {user_id})")
                
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
                
                if api_result and api_result.get('status') == 'ok':
                    logger.info("✅ API javobi OK. Natijani tekshirish uchun sahifa yangilanmoqda...")
                    
                    try:
                        self.page.reload(timeout=30000)
                        time.sleep(3)
                        
                        follow_btn = self.page.locator('button').filter(
                            has_text=re.compile(r"Follow|Obuna bo'lish|Подписаться|Takip et", re.IGNORECASE)
                        ).first
                        
                        if follow_btn.is_visible(timeout=5000):
                            database.update_status(username, 'unfollowed')
                            _, daily_unfollow = database.get_today_stats()
                            logger.info(f"{Fore.RED}🚫 Unfollow TASDIQLANDI: @{username} [{daily_unfollow}/{config.DAILY_UNFOLLOW_LIMIT}]")
                            return True
                        else:
                            following_check = self.page.locator('button').filter(
                                has_text=re.compile(r"Following|Requested|Obuna bo'lingan", re.IGNORECASE)
                            ).first
                            if following_check.is_visible(timeout=5000):
                                logger.warning(f"⚠️ API 'ok' dedi, lekin hali ham 'Following' turibdi @{username}")
                            else:
                                logger.warning(f"⚠️ Sahifada na Follow, na Following tugmasi topildi @{username}")
                    except Exception as verify_error:
                        logger.warning(f"⚠️ Verifikatsiya xatosi (30s timeout?): {verify_error}")
                        database.update_status(username, 'unfollowed')
                        _, daily_unfollow = database.get_today_stats()
                        logger.info(f"{Fore.YELLOW}🚫 Unfollow (API orqali, UI tasdiqsiz): @{username} [{daily_unfollow}/{config.DAILY_UNFOLLOW_LIMIT}]")
                        return True

                else:
                    logger.warning(f"⚠️ API Unfollow muvaffaqiyatsiz @{username}: {api_result}. UI ga o'tilmoqda...")
            
            # 4. FALLBACK: UI orqali Unfollow
            return self._unfollow_via_ui(username)
                
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                raise e
            logger.error(f"❌ Unfollow xatosi @{username}: {e}")
            
            fail_count = database.increment_fail_count(username)
            if fail_count >= 3:
                database.mark_as_blocked(username)
            
            return False
    
    def _unfollow_via_ui(self, username: str) -> bool:
        """UI orqali unfollow qilish (Fallback)"""
        try:
            # Header section topish
            header_section = self.page.locator('header section').first
            if not header_section.is_visible():
                header_section = self.page.locator('main header').first
            
            # Following tugmasi
            following_btn = header_section.locator('button').filter(
                has_text=re.compile(r"Following|Requested|Подписки|Запрос|Obuna bo'lingan|So'rov yuborilgan|Takip", re.IGNORECASE)
            ).first
            
            if not following_btn.is_visible():
                # Follow tugmasi bormi?
                follow_btn = header_section.locator('button').filter(
                    has_text=re.compile(r"Follow|Obuna bo'lish|Подписаться|Takip et", re.IGNORECASE)
                ).first
                
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
            unfollow_btn = dialog.locator('button').filter(
                has_text=re.compile(r"Unfollow|Отменить|Obunani bekor qilish|Takibi Bırak|Bekor qilish", re.IGNORECASE)
            ).first
            
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
            logger.error(f"❌ UI Unfollow xatosi @{username}: {e}")
            return False
    
    def _refresh_page(self):
        """Sahifani yangilash"""
        try:
            logger.info("🔄 Sahifa yangilanmoqda (60s timeout)...")
            self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
        except Exception as e:
            logger.warning(f"⚠️ Sahifa yangilashda xato: {e}")
    
    def check_and_unfollow(self):
        """24 soat o'tganlarni tekshirish va unfollow qilish"""
        logger.info("🔍 24 soat tekshiruvi boshlanmoqda...")
        
        waiting_users = database.get_waiting_users_for_unfollow(50)
        if not waiting_users:
            logger.info("✅ Tekshiradiganlar yo'q")
            return

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
            if database.get_config("current_cycle") not in ['cleanup', 'auto']:
                logger.info("⚡ Unfollow to'xtatildi (Yangi buyruq)")
                break

            if self.unfollow_user(username):
                delay = get_human_delay(config.UNFOLLOW_DELAY_MIN, config.UNFOLLOW_DELAY_MAX)
                logger.info(f"⏳ {delay} sekund kutilmoqda...")
                time.sleep(delay)
    
    def smart_cleanup_interactive(self):
        """
        SMART CLEANUP - Real-time GraphQL API orqali:
        1. O'z followerlarimni olish
        2. O'z followinglarimni olish
        3. Solishtirish va unfollow qilish
        """
        from colorama import Style
        
        logger.info(f"\n{Fore.YELLOW}{'='*50}")
        logger.info("🧹 SMART CLEANUP (REAL-TIME GraphQL API)")
        logger.info(f"{'='*50}{Style.RESET_ALL}")
        
        try:
            # 1. O'z User ID ni olish
            my_user_id = self.api.get_my_user_id()
            if not my_user_id:
                logger.error("❌ User ID olinmadi!")
                return
            
            logger.info(f"✅ Mening User ID: {my_user_id}")
            
            # 2. Real-time FOLLOWERS olish
            logger.info("📥 Real-time followerlar olinmoqda...")
            my_followers = set(self.api.fetch_followers_api(my_user_id, max_count=2000))
            logger.info(f"✅ {len(my_followers)} ta follower topildi")
            
            # 3. Real-time FOLLOWING olish
            logger.info("📥 Real-time following olinmoqda...")
            my_following = self.api.fetch_following_api(my_user_id, max_count=2000)
            logger.info(f"✅ {len(my_following)} ta following topildi")
            
            # 4. Solishtirish
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
                    
                    if self.unfollow_user(username):
                        unfollow_count += 1
                        
                        if unfollow_count % 5 == 0:
                            try:
                                import backup
                                backup.backup_cookies_to_gist(self.context.cookies())
                            except:
                                pass
                        
                        time.sleep(random.uniform(5, 10))
                
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
