"""
Instagram Session Creator with Challenge Support
Tasdiqlash kodlarini interaktiv qabul qiladi
"""

import json
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired

import config


def challenge_code_handler(username, choice):
    """Challenge kod so'rash"""
    print(f"\n⚠️  Instagram tasdiqlash talab qilmoqda!")
    print(f"📧 Tasdiqlash usuli: {choice}")
    code = input(f"📲 Tasdiqlash kodini kiriting: ").strip()
    return code


def create_session():
    """Session yaratish"""
    print("\n" + "="*50)
    print("🔐 INSTAGRAM SESSION YARATISH")
    print("="*50 + "\n")
    
    client = Client()
    
    # Challenge handler o'rnatish
    client.challenge_code_handler = challenge_code_handler
    
    # Sozlamalar
    client.delay_range = [1, 3]
    
    try:
        print(f"📱 @{config.INSTAGRAM_USERNAME} ga kirilmoqda...")
        
        # Login
        client.login(
            config.INSTAGRAM_USERNAME, 
            config.INSTAGRAM_PASSWORD
        )
        
        # Session saqlash
        client.dump_settings(Path(config.SESSION_FILE))
        print(f"\n✅ Session muvaffaqiyatli saqlandi!")
        
        # Test
        try:
            user_info = client.account_info()
            print(f"\n📊 AKKAUNT MA'LUMOTLARI:")
            print(f"   👤 Username: @{user_info.username}")
            print(f"   📝 Full name: {user_info.full_name}")
            print(f"   👥 Followers: {user_info.follower_count}")
            print(f"   👤 Following: {user_info.following_count}")
        except:
            print("✅ Login muvaffaqiyatli!")
        
        print("\n" + "="*50)
        print("✅ Endi asosiy botni ishga tushirishingiz mumkin:")
        print("   python bot.py")
        print("="*50 + "\n")
        
        return True
        
    except ChallengeRequired as e:
        print(f"\n⚠️  Challenge talab qilindi!")
        print(f"   Telefoningizda Instagram ilovasini oching va kirishni tasdiqlang.")
        return False
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Xato: {error_msg}")
        
        if "password" in error_msg.lower():
            print("\n💡 Parol noto'g'ri bo'lishi mumkin!")
            print("   config.py faylida parolni tekshiring.")
            
        elif "challenge" in error_msg.lower():
            print("\n💡 Instagram tasdiqlash talab qilmoqda!")
            print("   Telefoningizda Instagram ilovasini oching.")
            
        elif "wait" in error_msg.lower():
            print("\n💡 Juda ko'p urinish! Biroz kuting.")
            
        return False


if __name__ == "__main__":
    create_session()
