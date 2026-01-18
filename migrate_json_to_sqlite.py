import json
import sqlite3
from datetime import datetime
from pathlib import Path

JSON_FILE = "following_data.json"
DB_FILE = "bot.db"

def migrate():
    if not Path(JSON_FILE).exists():
        print(f"❌ {JSON_FILE} topilmadi. Migratsiya bekor qilindi.")
        return

    print(f"🔄 Migratsiya boshlanmoqda: {JSON_FILE} -> {DB_FILE}")

    try:
        # JSON o'qish
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # DB ulanish
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Jadvallarni yaratish (agar yo'q bo'lsa)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                status TEXT DEFAULT 'waiting',
                followed_at TIMESTAMP,
                unfollowed_at TIMESTAMP,
                checked BOOLEAN DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                follow_count INTEGER DEFAULT 0,
                unfollow_count INTEGER DEFAULT 0
            )
        """)
        
        # Ma'lumotlarni ko'chirish
        count = 0
        following = data.get("following", {})
        
        for user_id, user_data in following.items():
            username = user_data.get("username")
            status = user_data.get("status", "waiting")
            followed_at = user_data.get("followed_at")
            unfollowed_at = user_data.get("unfollowed_at")
            
            # Timestamp formatini to'g'irlash (agar kerak bo'lsa)
            try:
                datetime.fromisoformat(followed_at)
            except:
                followed_at = datetime.now().isoformat()

            cursor.execute("""
                INSERT OR IGNORE INTO users (username, status, followed_at, unfollowed_at, checked)
                VALUES (?, ?, ?, ?, 0)
            """, (username, status, followed_at, unfollowed_at))
            count += 1
            
        conn.commit()
        conn.close()
        
        print(f"✅ {count} ta foydalanuvchi muvaffaqiyatli o'tkazildi!")
        
    except Exception as e:
        print(f"❌ Xatolik yuz berdi: {e}")

if __name__ == "__main__":
    migrate()
