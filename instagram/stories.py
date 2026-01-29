"""
Instagram Bot - Story Watching
Story ko'rish va like bosish funksiyalari
"""

import re
import time
import random
import logging
from colorama import Fore

import database
from .utils import update_heartbeat, send_telegram_msg, refresh_page_if_stuck

logger = logging.getLogger(__name__)


class InstagramStories:
    """Story ko'rish va like bosish"""
    
    def __init__(self, page, context=None):
        self.page = page
        self.context = context
        self.last_seen_story_user = None
        self.debug_sent = False
    
    def _restart_story_viewing(self, skip_first: bool = True) -> bool:
        """Storylarni qayta boshlash uchun helper funksiya."""
        logger.info("🔄 _restart_story_viewing funksiyasi chaqirildi...")
        try:
            update_heartbeat()
            
            # 1. Home sahifaga o'tish
            self.page.goto("https://www.instagram.com/", wait_until="commit", timeout=20000)
            time.sleep(3)
            
            # 2. Story ringlarni topish
            story_rings = self.page.locator('canvas')
            ring_count = story_rings.count()
            
            if ring_count > 1:
                logger.info(f"🔄 {ring_count} ta story (canvas) topildi. Qayta boshlanmoqda...")
                
                if skip_first and ring_count > 2:
                    start_idx = min(2, ring_count - 1)
                    end_idx = min(ring_count - 1, 5)
                    selected_idx = random.randint(start_idx, end_idx) if start_idx < end_idx else start_idx
                    logger.info(f"🎲 Tasodifiy story tanlandi: #{selected_idx + 1}/{ring_count}")
                    story_rings.nth(selected_idx).click()
                else:
                    story_rings.nth(1).click()
                
                time.sleep(3)
                
                if "instagram.com/stories" in self.page.url:
                    logger.info("✅ Story ochildi!")
                    return True
                else:
                    logger.warning("⚠️ Story ochilmadi, URL tekshiruvi muvaffaqiyatsiz")
                    return False
            elif ring_count == 1:
                story_rings.first.click()
                time.sleep(3)
                if "instagram.com/stories" in self.page.url:
                    return True
                return False
            
            # Fallback: Role=button div
            try:
                stories = self.page.locator('div[role="button"]').filter(
                    has_text=re.compile(r"Story|Hikoya|История", re.IGNORECASE)
                )
                if stories.count() > 0:
                    stories.first.click()
                    time.sleep(2)
                    return True
            except:
                pass
            
            # Section bilan
            try:
                story_section = self.page.locator('section').first.locator('div[role="button"]').first
                if story_section.is_visible():
                    story_section.click()
                    time.sleep(2)
                    return True
            except:
                pass
            
            logger.warning("⚠️ Story topilmadi (qayta urinish)")
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Story qayta boshlashda xato: {e}")
            return False
    
    def watch_stories_and_like(self, duration: int, wait_remaining: bool = True):
        """
        Storylarni tomosha qilish va like bosish (Human-Like Behavior)
        
        Args:
            duration: Maksimal vaqt (sekund)
            wait_remaining: True bo'lsa qolgan vaqtni kutadi
        """
        initial_cycle = database.get_config("current_cycle", "auto")
        logger.info(f"🍿 Story tomosha qilish rejimi: {duration} sekund... (Mode: {initial_cycle})")
        
        start_time = time.time()
        
        # Immediate check
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
                    if "instagram.com" not in self.page.url: 
                        raise goto_err
                time.sleep(3)
            
            # 2. Story tray topish
            story_rings = self.page.locator('canvas')
            ring_count = story_rings.count()
            
            if ring_count > 0:
                logger.info(f"✅ {ring_count} ta story (canvas) topildi.")
                if ring_count > 1:
                    story_rings.nth(1).click()
                else:
                    story_rings.first.click()
                time.sleep(3)
            else:
                # Fallback
                stories = self.page.locator('div[role="button"]').filter(
                    has_text=re.compile(r"Story|Hikoya|История", re.IGNORECASE)
                )
                if stories.count() > 0:
                    stories.first.click()
                    time.sleep(2)
                else:
                    logger.warning("⚠️ Storylar topilmadi. Shunchaki kutilmoqda...")
                    time.sleep(duration)
                    return

            # 3. Loop: Story ko'rish
            same_user_count = 0
            last_user = None
            stuck_users = set()
            total_stuck_retries = 0
            max_total_stuck_retries = 15
            
            while (time.time() - start_time) < duration:
                update_heartbeat()

                remaining = duration - (time.time() - start_time)
                if remaining <= 0:
                    break
                
                watch_time = min(random.randint(3, 10), remaining)
                
                # Username aniqlash
                current_username = self._get_current_story_username()
                
                # Stuck detection
                if current_username == last_user:
                    same_user_count += 1
                    if same_user_count >= 3:
                        if current_username != "Noma'lum":
                            stuck_users.add(current_username)
                        
                        remaining = duration - (time.time() - start_time)
                        total_stuck_retries += 1
                        
                        if total_stuck_retries >= max_total_stuck_retries:
                            logger.warning(f"⚠️ Juda ko'p qotib qolish ({total_stuck_retries} marta). Chiqilmoqda...")
                            break
                        
                        if remaining > 30:
                            logger.warning(f"⚠️ Story qotib qoldi ({current_username} 3+ marta). Skip qilinmoqda...")
                            
                            if self._skip_to_next_story(current_username, stuck_users):
                                same_user_count = 0
                                last_user = None
                                continue
                            else:
                                # Sahifa yangilash
                                refresh_page_if_stuck(self.page)
                                time.sleep(2)
                                if self._restart_story_viewing():
                                    same_user_count = 0
                                    last_user = None
                                    continue
                        else:
                            logger.warning(f"⚠️ Story qotib qoldi. Chiqilmoqda...")
                            break
                else:
                    same_user_count = 0
                    last_user = current_username
                
                # Stuck userlarni skip
                if current_username in stuck_users:
                    logger.info(f"⏭️ @{current_username} avval qotib qolgan edi. Skip qilinmoqda...")
                    self._skip_multiple_stories(5)
                    continue

                logger.info(f"👀 Story ko'rilmoqda: @{current_username} ({watch_time}s)")
                
                # Telegram xabar
                if self.last_seen_story_user != current_username:
                    msg_text = f"👀 <b>Story ko'rilmoqda:</b> "
                    if current_username != "Noma'lum":
                        msg_text += f"<a href='https://instagram.com/{current_username}'>@{current_username}</a>"
                    else:
                        msg_text += "<i>(Yashirin profi)</i>"
                    send_telegram_msg(msg_text)
                    self.last_seen_story_user = current_username

                # Buyruq tekshirish
                current_cycle_check = database.get_config("current_cycle", "auto")
                if current_cycle_check != initial_cycle:
                    logger.info(f"⚡ Story ko'rish to'xtatildi (Yangi buyruq: {current_cycle_check})")
                    break

                time.sleep(watch_time)
                
                # Random Like (85%)
                if random.random() < 0.85:
                    self._try_like_story(current_username)
                
                # Keyingi story
                self._go_to_next_story()
                
                # Storylar tugaganmi?
                if "instagram.com/stories" not in self.page.url:
                    remaining = duration - (time.time() - start_time)
                    if remaining > 30:
                        logger.info(f"🔄 Storylar tugadi. Qayta boshlanmoqda... ({int(remaining)}s qoldi)")
                        time.sleep(3)
                        if self._restart_story_viewing():
                            same_user_count = 0
                            last_user = None
                            continue
                    logger.info("✅ Barcha storylar ko'rildi.")
                    break

        except Exception as e:
            logger.error(f"❌ Story ko'rishda xato: {e}")
        
        # Qolgan vaqt
        if not wait_remaining:
            logger.info("✅ Storylar tugadi. Darhol davom etilmoqda.")
            return
        
        self._handle_remaining_time(duration, start_time, initial_cycle)
    
    def _get_current_story_username(self) -> str:
        """Hozirgi story egasining usernameni olish"""
        current_username = "Noma'lum"
        
        for _ in range(3):
            try:
                url = self.page.url
                match = re.search(r"stories/([^/]+)/", url)
                if match:
                    current_username = match.group(1)
                    break
                
                if current_username == "Noma'lum":
                    user_el = self.page.locator('header a').first
                    if user_el.is_visible():
                        current_username = user_el.inner_text()
                        if current_username != "Noma'lum": 
                            break
                
                if current_username == "Noma'lum":
                    header_text = self.page.locator('header').first.inner_text()
                    lines = header_text.split('\n')
                    if lines:
                        current_username = lines[0]
                        if current_username != "Noma'lum": 
                            break
            except:
                pass
            
            time.sleep(0.5)
        
        return current_username
    
    def _skip_to_next_story(self, current_username: str, stuck_users: set) -> bool:
        """Keyingi storyga o'tish"""
        for skip_attempt in range(10):
            try:
                self.page.keyboard.press("ArrowRight")
                time.sleep(0.5)
                
                new_url = self.page.url
                new_match = re.search(r"stories/([^/]+)/", new_url)
                if new_match:
                    new_username = new_match.group(1)
                    if new_username != current_username and new_username not in stuck_users:
                        logger.info(f"✅ Keyingi userga o'tildi: @{new_username}")
                        return True
            except:
                pass
        
        # Next tugmani bosish
        try:
            next_btns = self.page.locator('svg[aria-label="Next"], svg[aria-label="Right chevron"], svg[aria-label="Keyingisi"]')
            if next_btns.count() > 0:
                for i in range(next_btns.count()):
                    btn = next_btns.nth(i)
                    if btn.is_visible():
                        btn.locator("..").click(force=True)
                        time.sleep(1)
                        return True
        except:
            pass
        
        return False
    
    def _skip_multiple_stories(self, count: int):
        """Bir nechta story o'tkazib yuborish"""
        try:
            for _ in range(count):
                self.page.keyboard.press("ArrowRight")
                time.sleep(0.3)
        except:
            pass
    
    def _try_like_story(self, current_username: str):
        """Storyga like bosishga urinish"""
        try:
            unlike_selector = (
                'svg[aria-label*="Unlike"], '
                'svg[aria-label*="O\'chirish"], '
                'svg[aria-label*="Yoqtirishni bekor qilish"], '
                'svg[aria-label*="Vazgeç"], '
                'svg[aria-label*="Je n\'aime plus"]'
            )
            
            unlike_svgs = self.page.locator(unlike_selector)
            is_liked = False
            clicked = False
            
            for i in range(unlike_svgs.count()):
                if unlike_svgs.nth(i).is_visible():
                    is_liked = True
                    break
            
            if is_liked:
                logger.info(f"ℹ️ {current_username}: Storyga allaqachon like bosilgan.")
            else:
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
                
                for i in range(count):
                    svg = like_svgs.nth(i)
                    if svg.is_visible():
                        try:
                            like_btn = svg.locator("..")
                            like_btn.click(force=True)
                            clicked = True
                            logger.info(f"{Fore.MAGENTA}❤️ Storyga Like bosildi!")
                            
                            if "Noma'lum" in current_username:
                                user_display = f"<i>{current_username}</i>"
                            else:
                                user_display = f"<a href='https://instagram.com/{current_username}'>@{current_username}</a>"
                            
                            send_telegram_msg(f"❤️ <b>Storyga Like bosildi:</b> {user_display}")
                            time.sleep(1)
                            break
                        except Exception as click_err:
                            logger.warning(f"⚠️ Like tugmasini bosishda muammo: {click_err}")
                            continue
            
            if not clicked and not is_liked:
                if not self.debug_sent:
                    try:
                        all_labels = self.page.locator('svg[aria-label]').evaluate_all(
                            "els => els.map(e => e.getAttribute('aria-label'))"
                        )
                        readable_labels = [str(l) for l in all_labels if l and len(l) < 30] 
                        logger.warning(f"⚠️ Like topilmadi. Mavjud: {readable_labels}")
                        if readable_labels:
                            send_telegram_msg(f"⚠️ <b>DEBUG (Like topilmadi):</b>\nEkranda: {', '.join(readable_labels)}")
                            self.debug_sent = True
                    except Exception as e:
                        logger.error(f"Debug Error: {e}")
        except Exception as e:
            logger.error(f"Like Error: {e}")
    
    def _go_to_next_story(self):
        """Keyingi storyga o'tish"""
        try:
            old_url = self.page.url
            
            # 1. Next tugmasi
            next_btns = self.page.locator('svg[aria-label="Next"], svg[aria-label="Right chevron"], svg[aria-label="Keyingisi"]')
            if next_btns.count() > 0:
                for i in range(next_btns.count()):
                    btn = next_btns.nth(i)
                    if btn.is_visible():
                        try:
                            btn.locator("..").click(force=True)
                            time.sleep(0.5)
                            break
                        except:
                            pass
            
            if self.page.url != old_url:
                return
            
            # 2. Keyboard Right
            for _ in range(3):
                self.page.keyboard.press("ArrowRight")
                time.sleep(0.2)
            
            if self.page.url != old_url:
                return

            # 3. Mouse click
            try:
                viewport = self.page.viewport_size
                if viewport:
                    x = int(viewport['width'] * 0.95)
                    y = int(viewport['height'] * 0.5)
                    self.page.mouse.click(x, y)
                    time.sleep(0.5)
            except:
                pass
        except:
            pass
    
    def _handle_remaining_time(self, duration: int, start_time: float, initial_cycle: str):
        """Qolgan vaqtni boshqarish"""
        remaining = duration - (time.time() - start_time)
        restart_attempts = 0
        max_restart_attempts = 10
        
        while remaining > 60 and restart_attempts < max_restart_attempts:
            logger.info(f"🔄 Vaqt qoldi ({int(remaining)}s). Qayta boshlaymiz ({restart_attempts + 1}/{max_restart_attempts})...")
            restart_attempts += 1
            time.sleep(5)
            
            current_cycle_check = database.get_config("current_cycle", "auto")
            if current_cycle_check != initial_cycle:
                logger.info(f"⚡ Qayta boshlash to'xtatildi (Yangi buyruq: {current_cycle_check})")
                return
            
            if self._restart_story_viewing():
                try:
                    sub_start = time.time()
                    max_iterations = 100
                    iterations = 0
                    
                    while (time.time() - sub_start) < remaining and iterations < max_iterations:
                        update_heartbeat()
                        iterations += 1
                        
                        sub_remaining = remaining - (time.time() - sub_start)
                        if sub_remaining <= 0:
                            break
                        
                        if "instagram.com/stories" not in self.page.url:
                            logger.info("🔚 Storylar tugadi (sub-loop).")
                            break
                        
                        watch_time = min(random.randint(3, 8), sub_remaining)
                        logger.info(f"👀 Story (sub): {watch_time}s kutilmoqda...")
                        time.sleep(watch_time)
                        
                        self.page.keyboard.press("ArrowRight")
                        time.sleep(0.5)
                        
                        try:
                            viewport = self.page.viewport_size
                            if viewport:
                                x = int(viewport['width'] * 0.85)
                                y = int(viewport['height'] * 0.5)
                                self.page.mouse.click(x, y)
                                time.sleep(0.3)
                        except:
                            pass
                        
                except Exception as restart_err:
                    logger.warning(f"⚠️ Qayta ko'rish xatosi: {restart_err}")
            
            remaining = duration - (time.time() - start_time)
        
        # Qolgan vaqt
        remaining = min(remaining, 60)
        if remaining > 0:
            logger.info(f"⏳ Qolgan vaqt: {int(remaining)}s. (Buyruqlar kutilmoqda...)")
            slept = 0
            while slept < remaining:
                time.sleep(1)
                slept += 1
                current_cycle_check = database.get_config("current_cycle", "auto")
                if current_cycle_check != initial_cycle:
                    logger.info(f"⚡ Kutish to'xtatildi (Yangi buyruq: {current_cycle_check})")
                    break
