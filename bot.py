"""
Instagram Follow/Unfollow Bot
Yangi odamlarni follow qiladi, 24 soatdan keyin tekshiradi, va qaytarmaganlarni unfollow qiladi.

Xususiyatlar:
- Tungi dam olish (00:00 - 07:00)
- Insoniy vaqt oralig'i (2-5 daqiqa)
- Baza orqali follow qilinganlarni kuzatish
- 24 soatdan keyin avtomatik tekshirish va unfollow
"""

import json
import time
import random
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from colorama import init, Fore, Style

# Instagrapi import
try:
    from instagrapi import Client
    from instagrapi.exceptions import (
        LoginRequired, 
        ChallengeRequired,
        TwoFactorRequired,
        BadPassword,
        UserNotFound,
        RateLimitError
    )
except ImportError:
    print(f"{Fore.RED}❌ instagrapi kutubxonasi topilmadi!")
    print(f"{Fore.YELLOW}Iltimos, quyidagini bajaring: pip install instagrapi{Style.RESET_ALL}")
    exit(1)

import config

# Colorama init
init(autoreset=True)

# Logger sozlash
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class InstagramBot:
    """Instagram avtomatik follow/unfollow bot"""
    
    def __init__(self):
        self.client = Client()
        self.client.delay_range = [1, 3]  # Request orasidagi delay
        self.following_data = self._load_following_data()
        self.daily_follow_count = 0
        self.daily_unfollow_count = 0
        self.last_reset_date = datetime.now().date()
        
    def _load_following_data(self) -> dict:
        """Follow qilinganlar ro'yxatini yuklash (BAZA)"""
        if Path(config.FOLLOWING_DB).exists():
            try:
                with open(config.FOLLOWING_DB, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"📂 Bazadan {len(data.get('following', {}))} ta yozuv yuklandi")
                    return data
            except json.JSONDecodeError:
                return {"following": {}, "stats": {"total_followed": 0, "total_unfollowed": 0, "followed_back": 0}}
        return {"following": {}, "stats": {"total_followed": 0, "total_unfollowed": 0, "followed_back": 0}}
    
    def _save_following_data(self):
        """Follow qilinganlar ro'yxatini saqlash (BAZA)"""
        with open(config.FOLLOWING_DB, 'w', encoding='utf-8') as f:
            json.dump(self.following_data, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Baza saqlandi: {len(self.following_data['following'])} ta yozuv")
    
    def _reset_daily_counters(self):
        """Kunlik hisoblagichlarni resetlash"""
        today = datetime.now().date()
        if today > self.last_reset_date:
            self.daily_follow_count = 0
            self.daily_unfollow_count = 0
            self.last_reset_date = today
            logger.info(f"{Fore.CYAN}📊 Yangi kun! Kunlik hisoblagichlar resetlandi")
    
    def is_night_time(self) -> bool:
        """Tungi vaqtda ekanligini tekshirish"""
        current_hour = datetime.now().hour
        if config.NIGHT_REST_START <= current_hour or current_hour < config.NIGHT_REST_END:
            return True
        return False
    
    def wait_until_morning(self):
        """Tongga qadar kutish"""
        now = datetime.now()
        
        # Keyingi 07:00 ni hisoblash
        if now.hour >= config.NIGHT_REST_START or now.hour < config.NIGHT_REST_END:
            # Tonggi 07:00
            if now.hour >= config.NIGHT_REST_START:
                # Bugungi tun, ertangi tongga kutish
                tomorrow = now + timedelta(days=1)
                wake_time = tomorrow.replace(hour=config.NIGHT_REST_END, minute=0, second=0, microsecond=0)
            else:
                # Ertalabki tun, shu kungi tongga kutish
                wake_time = now.replace(hour=config.NIGHT_REST_END, minute=0, second=0, microsecond=0)
            
            wait_seconds = (wake_time - now).total_seconds()
            
            print(f"\n{Fore.CYAN}{'='*50}")
            print(f"{Fore.YELLOW}🌙 TUNGI DAM OLISH VAQTI")
            print(f"{Fore.WHITE}   Hozir: {now.strftime('%H:%M')}")
            print(f"{Fore.WHITE}   Uyg'onish: {wake_time.strftime('%H:%M')}")
            print(f"{Fore.WHITE}   Kutish: {wait_seconds/3600:.1f} soat")
            print(f"{Fore.CYAN}{'='*50}\n")
            
            time.sleep(wait_seconds)
            logger.info(f"{Fore.GREEN}☀️ Tong bo'ldi! Bot yana ishlamoqda...")
    
    def get_human_delay(self, delay_min: int, delay_max: int) -> int:
        """Insoniy vaqt oralig'ini olish (tasodifiy)"""
        # Gauss taqsimoti bilan yanada tabiiy kutish
        mean = (delay_min + delay_max) / 2
        std = (delay_max - delay_min) / 4
        delay = int(random.gauss(mean, std))
        # Limitlar ichida bo'lishini ta'minlash
        return max(delay_min, min(delay_max, delay))
    
    def login(self) -> bool:
        """Instagram'ga kirish"""
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.YELLOW}🔐 Instagram'ga kirilmoqda...")
        print(f"{Fore.CYAN}{'='*50}\n")
        
        # Oldingi session'ni yuklashga harakat
        session_file = Path(config.SESSION_FILE)
        if session_file.exists():
            try:
                logger.info("📂 Oldingi session yuklanmoqda...")
                self.client.load_settings(session_file)
                self.client.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)
                self.client.get_timeline_feed()  # Session ishlayotganini tekshirish
                logger.info(f"{Fore.GREEN}✅ Session muvaffaqiyatli yuklandi!")
                return True
            except Exception as e:
                logger.warning(f"⚠️ Session eskirgan, yangi login qilinmoqda: {e}")
        
        # Yangi login
        try:
            self.client.login(config.INSTAGRAM_USERNAME, config.INSTAGRAM_PASSWORD)
            self.client.dump_settings(session_file)
            logger.info(f"{Fore.GREEN}✅ Muvaffaqiyatli login bo'ldi: @{config.INSTAGRAM_USERNAME}")
            return True
            
        except BadPassword:
            logger.error(f"{Fore.RED}❌ Noto'g'ri parol!")
            return False
            
        except TwoFactorRequired:
            logger.warning(f"{Fore.YELLOW}🔐 2FA talab qilinmoqda...")
            code = input(f"{Fore.CYAN}SMS yoki Authenticator kodini kiriting: {Style.RESET_ALL}")
            try:
                self.client.login(
                    config.INSTAGRAM_USERNAME, 
                    config.INSTAGRAM_PASSWORD,
                    verification_code=code
                )
                self.client.dump_settings(session_file)
                logger.info(f"{Fore.GREEN}✅ 2FA bilan login muvaffaqiyatli!")
                return True
            except Exception as e:
                logger.error(f"{Fore.RED}❌ 2FA login xatosi: {e}")
                return False
                
        except ChallengeRequired:
            logger.error(f"{Fore.RED}❌ Instagram challenge talab qilmoqda. Telefon orqali tasdiqlang!")
            return False
            
        except Exception as e:
            logger.error(f"{Fore.RED}❌ Login xatosi: {e}")
            return False
    
    def get_target_users(self, count: int = 50) -> list:
        """Target foydalanuvchilarni olish"""
        users = []
        
        try:
            if config.TARGET_ACCOUNT:
                logger.info(f"🎯 @{config.TARGET_ACCOUNT} followerlarini olmoqda...")
                user_id = self.client.user_id_from_username(config.TARGET_ACCOUNT)
                followers = self.client.user_followers(user_id, amount=count)
                users = list(followers.values())
                logger.info(f"✅ {len(users)} ta follower topildi")
                
            elif config.TARGET_HASHTAG:
                logger.info(f"🏷️ #{config.TARGET_HASHTAG} bo'yicha qidirilmoqda...")
                medias = self.client.hashtag_medias_recent(config.TARGET_HASHTAG, amount=count)
                for media in medias:
                    if media.user not in users:
                        users.append(media.user)
                logger.info(f"✅ {len(users)} ta foydalanuvchi topildi")
                
        except UserNotFound:
            logger.error(f"{Fore.RED}❌ Target akkaunt topilmadi: @{config.TARGET_ACCOUNT}")
        except Exception as e:
            logger.error(f"{Fore.RED}❌ Foydalanuvchilarni olishda xato: {e}")
            
        return users
    
    def follow_user(self, user) -> bool:
        """Foydalanuvchini follow qilish"""
        self._reset_daily_counters()
        
        # Tungi vaqtni tekshirish
        if self.is_night_time():
            self.wait_until_morning()
        
        if self.daily_follow_count >= config.DAILY_FOLLOW_LIMIT:
            logger.warning(f"{Fore.YELLOW}⚠️ Kunlik follow limiti tugadi ({config.DAILY_FOLLOW_LIMIT})")
            return False
        
        user_id = str(user.pk)
        
        # Allaqachon follow qilinganmi tekshirish (bazadan)
        if user_id in self.following_data["following"]:
            logger.info(f"⏭️ @{user.username} allaqachon bazada, o'tkazildi")
            return False
        
        try:
            self.client.user_follow(user.pk)
            
            # Bazaga yozish
            self.following_data["following"][user_id] = {
                "username": user.username,
                "full_name": user.full_name or "",
                "followed_at": datetime.now().isoformat(),
                "check_after": (datetime.now() + timedelta(hours=24)).isoformat(),
                "status": "waiting",  # waiting, followed_back, unfollowed
                "checked": False
            }
            
            # Statistikani yangilash
            if "stats" not in self.following_data:
                self.following_data["stats"] = {"total_followed": 0, "total_unfollowed": 0, "followed_back": 0}
            self.following_data["stats"]["total_followed"] += 1
            
            self._save_following_data()
            
            self.daily_follow_count += 1
            logger.info(f"{Fore.GREEN}✅ Follow qilindi: @{user.username} [{self.daily_follow_count}/{config.DAILY_FOLLOW_LIMIT}]")
            return True
            
        except RateLimitError:
            logger.error(f"{Fore.RED}❌ Rate limit! 10 daqiqa kutilmoqda...")
            time.sleep(600)
            return False
        except Exception as e:
            logger.error(f"{Fore.RED}❌ Follow xatosi @{user.username}: {e}")
            return False
    
    def check_followers_back(self):
        """24 soatdan keyin follow qaytarganlarni tekshirish"""
        logger.info(f"\n{Fore.CYAN}🔍 Follow qaytarganlar tekshirilmoqda...")
        
        try:
            # O'z followerlarimizni olish
            my_user_id = self.client.user_id
            my_followers = self.client.user_followers(my_user_id, amount=0)
            my_followers_ids = set(str(f.pk) for f in my_followers.values())
            
            now = datetime.now()
            users_to_unfollow = []
            
            for user_id, data in list(self.following_data["following"].items()):
                if data.get("status") != "waiting":
                    continue
                    
                followed_at = datetime.fromisoformat(data["followed_at"])
                hours_passed = (now - followed_at).total_seconds() / 3600
                
                # 24 soat o'tganmi?
                if hours_passed >= 24:
                    if user_id in my_followers_ids:
                        # Follow qaytardi!
                        logger.info(f"{Fore.GREEN}✅ @{data['username']} follow qaytardi! ✨")
                        self.following_data["following"][user_id]["status"] = "followed_back"
                        self.following_data["following"][user_id]["checked"] = True
                        if "stats" in self.following_data:
                            self.following_data["stats"]["followed_back"] += 1
                    else:
                        # Follow qaytarmadi
                        users_to_unfollow.append({
                            "user_id": user_id,
                            "username": data["username"],
                            "hours_passed": hours_passed
                        })
                        logger.info(f"{Fore.YELLOW}❌ @{data['username']} follow qaytarmagan ({hours_passed:.1f} soat)")
            
            self._save_following_data()
            return users_to_unfollow
            
        except Exception as e:
            logger.error(f"{Fore.RED}❌ Tekshirish xatosi: {e}")
            return []
    
    def unfollow_user(self, user_id: str, username: str) -> bool:
        """Foydalanuvchini unfollow qilish"""
        self._reset_daily_counters()
        
        # Tungi vaqtni tekshirish
        if self.is_night_time():
            self.wait_until_morning()
        
        if self.daily_unfollow_count >= config.DAILY_UNFOLLOW_LIMIT:
            logger.warning(f"{Fore.YELLOW}⚠️ Kunlik unfollow limiti tugadi ({config.DAILY_UNFOLLOW_LIMIT})")
            return False
        
        try:
            self.client.user_unfollow(int(user_id))
            
            # Bazani yangilash (o'chirmasdan status ni o'zgartirish)
            if user_id in self.following_data["following"]:
                self.following_data["following"][user_id]["status"] = "unfollowed"
                self.following_data["following"][user_id]["unfollowed_at"] = datetime.now().isoformat()
                if "stats" in self.following_data:
                    self.following_data["stats"]["total_unfollowed"] += 1
                self._save_following_data()
            
            self.daily_unfollow_count += 1
            logger.info(f"{Fore.RED}🚫 Unfollow qilindi: @{username} [{self.daily_unfollow_count}/{config.DAILY_UNFOLLOW_LIMIT}]")
            return True
            
        except RateLimitError:
            logger.error(f"{Fore.RED}❌ Rate limit! 10 daqiqa kutilmoqda...")
            time.sleep(600)
            return False
        except Exception as e:
            logger.error(f"{Fore.RED}❌ Unfollow xatosi @{username}: {e}")
            return False
    
    def run_follow_cycle(self, count: int = 20):
        """Follow siklini ishga tushirish"""
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.YELLOW}🚀 FOLLOW SIKLI BOSHLANDI")
        print(f"{Fore.CYAN}{'='*50}\n")
        
        # Tungi vaqtni tekshirish
        if self.is_night_time():
            self.wait_until_morning()
        
        users = self.get_target_users(count)
        
        if not users:
            logger.warning("⚠️ Follow qilish uchun foydalanuvchi topilmadi")
            return
        
        followed = 0
        for user in users:
            if self.follow_user(user):
                followed += 1
                # Insoniy vaqt oralig'i
                delay = self.get_human_delay(config.FOLLOW_DELAY_MIN, config.FOLLOW_DELAY_MAX)
                logger.info(f"⏳ {delay} sekund ({delay/60:.1f} daqiqa) kutilmoqda...")
                time.sleep(delay)
        
        logger.info(f"\n{Fore.GREEN}✅ Follow sikli tugadi: {followed} ta follow qilindi")
    
    def run_unfollow_cycle(self):
        """Unfollow siklini ishga tushirish"""
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.YELLOW}🔄 24 SOATLIK TEKSHIRISH VA UNFOLLOW")
        print(f"{Fore.CYAN}{'='*50}\n")
        
        # Tungi vaqtni tekshirish
        if self.is_night_time():
            self.wait_until_morning()
        
        users_to_unfollow = self.check_followers_back()
        
        if not users_to_unfollow:
            logger.info("✅ Unfollow qilish kerak bo'lgan foydalanuvchi yo'q")
            return
        
        unfollowed = 0
        for user in users_to_unfollow:
            if self.unfollow_user(user["user_id"], user["username"]):
                unfollowed += 1
                # Insoniy vaqt oralig'i
                delay = self.get_human_delay(config.UNFOLLOW_DELAY_MIN, config.UNFOLLOW_DELAY_MAX)
                logger.info(f"⏳ {delay} sekund ({delay/60:.1f} daqiqa) kutilmoqda...")
                time.sleep(delay)
        
        logger.info(f"\n{Fore.RED}🚫 Unfollow sikli tugadi: {unfollowed} ta unfollow qilindi")
    
    def show_stats(self):
        """Statistikani ko'rsatish"""
        total_following = len(self.following_data["following"])
        waiting = sum(1 for d in self.following_data["following"].values() if d.get("status") == "waiting")
        followed_back = sum(1 for d in self.following_data["following"].values() if d.get("status") == "followed_back")
        unfollowed = sum(1 for d in self.following_data["following"].values() if d.get("status") == "unfollowed")
        
        stats = self.following_data.get("stats", {})
        
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.YELLOW}📊 STATISTIKA (BAZA)")
        print(f"{Fore.CYAN}{'='*50}")
        print(f"{Fore.WHITE}📝 Jami bazadagi yozuvlar: {Fore.GREEN}{total_following}")
        print(f"{Fore.WHITE}⏳ Kutilmoqda (24 soat): {Fore.YELLOW}{waiting}")
        print(f"{Fore.WHITE}✅ Follow qaytardi: {Fore.GREEN}{followed_back}")
        print(f"{Fore.WHITE}🚫 Unfollow qilindi: {Fore.RED}{unfollowed}")
        print(f"{Fore.CYAN}{'='*50}")
        print(f"{Fore.WHITE}📅 Bugun follow: {Fore.GREEN}{self.daily_follow_count}/{config.DAILY_FOLLOW_LIMIT}")
        print(f"{Fore.WHITE}📅 Bugun unfollow: {Fore.RED}{self.daily_unfollow_count}/{config.DAILY_UNFOLLOW_LIMIT}")
        print(f"{Fore.CYAN}{'='*50}\n")
    
    def show_database(self):
        """Bazadagi ma'lumotlarni ko'rsatish"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.YELLOW}📁 BAZA MA'LUMOTLARI")
        print(f"{Fore.CYAN}{'='*60}")
        
        if not self.following_data["following"]:
            print(f"{Fore.WHITE}   Baza bo'sh")
        else:
            # Status bo'yicha guruhlash
            waiting = []
            followed_back = []
            unfollowed_list = []
            
            for user_id, data in self.following_data["following"].items():
                status = data.get("status", "waiting")
                if status == "waiting":
                    waiting.append(data)
                elif status == "followed_back":
                    followed_back.append(data)
                else:
                    unfollowed_list.append(data)
            
            # Kutilayotganlar
            if waiting:
                print(f"\n{Fore.YELLOW}⏳ KUTILMOQDA ({len(waiting)} ta):")
                for i, data in enumerate(waiting[:10], 1):
                    followed_at = datetime.fromisoformat(data["followed_at"])
                    hours = (datetime.now() - followed_at).total_seconds() / 3600
                    remaining = max(0, 24 - hours)
                    print(f"   {i}. @{data['username']} - {hours:.1f} soat o'tdi, {remaining:.1f} soat qoldi")
                if len(waiting) > 10:
                    print(f"   ... va yana {len(waiting) - 10} ta")
            
            # Follow qaytarganlar
            if followed_back:
                print(f"\n{Fore.GREEN}✅ FOLLOW QAYTARDI ({len(followed_back)} ta):")
                for i, data in enumerate(followed_back[:10], 1):
                    print(f"   {i}. @{data['username']}")
                if len(followed_back) > 10:
                    print(f"   ... va yana {len(followed_back) - 10} ta")
            
            # Unfollow qilinganlar
            if unfollowed_list:
                print(f"\n{Fore.RED}🚫 UNFOLLOW QILINDI ({len(unfollowed_list)} ta):")
                for i, data in enumerate(unfollowed_list[:10], 1):
                    print(f"   {i}. @{data['username']}")
                if len(unfollowed_list) > 10:
                    print(f"   ... va yana {len(unfollowed_list) - 10} ta")
        
        print(f"{Fore.CYAN}{'='*60}\n")


def main():
    """Asosiy funksiya"""
    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗
{Fore.CYAN}║{Fore.YELLOW}     📸 INSTAGRAM FOLLOW/UNFOLLOW BOT                         {Fore.CYAN}║
{Fore.CYAN}║{Fore.WHITE}     Avtomatik follow, 24 soat tekshirish va unfollow          {Fore.CYAN}║
{Fore.CYAN}║{Fore.WHITE}     🌙 Tungi dam olish: 00:00 - 07:00                          {Fore.CYAN}║
{Fore.CYAN}║{Fore.WHITE}     ⏱️  Insoniy vaqt: 2-5 daqiqa oralig'i                       {Fore.CYAN}║
{Fore.CYAN}╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
    """)
    
    bot = InstagramBot()
    
    # Login
    if not bot.login():
        print(f"{Fore.RED}❌ Login amalga oshmadi. Dastur tugatildi.")
        return
    
    # Menu
    while True:
        print(f"""
{Fore.CYAN}┌───────────────────────────────────────┐
{Fore.CYAN}│{Fore.YELLOW} 🎮 MENYU                              {Fore.CYAN}│
{Fore.CYAN}├───────────────────────────────────────┤
{Fore.CYAN}│{Fore.WHITE} 1. 🚀 Follow siklini boshlash         {Fore.CYAN}│
{Fore.CYAN}│{Fore.WHITE} 2. 🔄 24 soat tekshirish + unfollow   {Fore.CYAN}│
{Fore.CYAN}│{Fore.WHITE} 3. 🤖 Avtomatik rejim (24/7)          {Fore.CYAN}│
{Fore.CYAN}│{Fore.WHITE} 4. 📊 Statistika                      {Fore.CYAN}│
{Fore.CYAN}│{Fore.WHITE} 5. 📁 Bazani ko'rish                  {Fore.CYAN}│
{Fore.CYAN}│{Fore.WHITE} 6. 🚪 Chiqish                         {Fore.CYAN}│
{Fore.CYAN}└───────────────────────────────────────┘
        """)
        
        choice = input(f"{Fore.CYAN}Tanlang (1-6): {Style.RESET_ALL}").strip()
        
        if choice == "1":
            count = input(f"{Fore.CYAN}Nechta follow qilish kerak? (default: 20): {Style.RESET_ALL}").strip()
            count = int(count) if count.isdigit() else 20
            bot.run_follow_cycle(count)
            
        elif choice == "2":
            bot.run_unfollow_cycle()
            
        elif choice == "3":
            print(f"\n{Fore.YELLOW}🤖 AVTOMATIK REJIM BOSHLANDI")
            print(f"{Fore.WHITE}✅ Har soatda 20 ta follow qiladi")
            print(f"{Fore.WHITE}✅ 24 soatdan keyin tekshiradi")
            print(f"{Fore.WHITE}✅ Qaytarmaganlarni unfollow qiladi")
            print(f"{Fore.WHITE}🌙 Tungi 00:00-07:00 da dam oladi")
            print(f"{Fore.RED}❌ To'xtatish uchun Ctrl+C bosing\n")
            
            try:
                while True:
                    # Tungi vaqtni tekshirish
                    if bot.is_night_time():
                        bot.wait_until_morning()
                    
                    # Follow sikli
                    bot.run_follow_cycle(20)
                    bot.show_stats()
                    
                    # Unfollow sikli (24 soat o'tganlarni)
                    bot.run_unfollow_cycle()
                    bot.show_stats()
                    
                    # Keyingi siklgacha kutish (1 soat)
                    logger.info(f"⏳ Keyingi sikl uchun 1 soat kutilmoqda...")
                    time.sleep(3600)
                    
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}⚠️ Avtomatik rejim to'xtatildi")
            
        elif choice == "4":
            bot.show_stats()
            
        elif choice == "5":
            bot.show_database()
            
        elif choice == "6":
            print(f"\n{Fore.GREEN}👋 Xayr! Bot to'xtatildi.")
            break
        
        else:
            print(f"{Fore.RED}❌ Noto'g'ri tanlov!")


if __name__ == "__main__":
    main()
