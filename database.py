import sqlite3
import logging
from datetime import datetime
import config

logger = logging.getLogger(__name__)

DB_FILE = "bot.db"

def get_connection():
    """Baza bilan ulanish"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Jadvallarni yaratish"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Users jadvali
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'waiting', -- waiting, followed_back, unfollowed
                    followed_at TIMESTAMP,
                    unfollowed_at TIMESTAMP,
                    checked BOOLEAN DEFAULT 0
                )
            """)
            
            # Daily stats jadvali
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    follow_count INTEGER DEFAULT 0,
                    unfollow_count INTEGER DEFAULT 0
                )
            """)
            
            # Config jadvali (State management uchun)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            conn.commit()
            logger.info("✅ Baza ishga tushdi (users, daily_stats, config)")
    except Exception as e:
        logger.error(f"❌ Baza yaratish xatosi: {e}")

def add_user(username):
    """Yangi userni qo'shish (follow qilinganda)"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now()
            cursor.execute("""
                INSERT OR IGNORE INTO users (username, status, followed_at, checked)
                VALUES (?, 'waiting', ?, 0)
            """, (username, now))
            
            # Kunlik statistika
            date_str = now.date().isoformat()
            cursor.execute("""
                INSERT INTO daily_stats (date, follow_count, unfollow_count)
                VALUES (?, 1, 0)
                ON CONFLICT(date) DO UPDATE SET follow_count = follow_count + 1
            """, (date_str,))
            
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"❌ DB Add user error: {e}")
        return False

def add_pending_user(username, source_target=None):
    """Pending user qo'shish (hali follow qilinmagan, to'plangan)"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now()
            cursor.execute("""
                INSERT OR IGNORE INTO users (username, status, followed_at, checked)
                VALUES (?, 'pending', NULL, 0)
            """, (username,))
            conn.commit()
            return cursor.rowcount > 0  # True if actually inserted
    except Exception as e:
        logger.error(f"❌ DB Add pending user error: {e}")
        return False

def get_pending_users(count=20):
    """Pending statusdagi userlarni olish (follow qilish uchun)"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT username FROM users 
                WHERE status = 'pending' 
                ORDER BY ROWID ASC 
                LIMIT ?
            """, (count,))
            return [row['username'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"❌ DB Get pending users error: {e}")
        return []

def get_pending_count():
    """Pending statusdagi userlar soni"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE status = 'pending'")
            return cursor.fetchone()['cnt']
    except Exception as e:
        logger.error(f"❌ DB Get pending count error: {e}")
        return 0

def get_user(username):
    """User borligini tekshirish"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"❌ DB Get user error: {e}")
        return None

def update_status(username, status):
    """Statusni yangilash (followed_back, unfollowed)"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now()
            
            if status == 'unfollowed':
                cursor.execute("""
                    UPDATE users 
                    SET status = ?, unfollowed_at = ? 
                    WHERE username = ?
                """, (status, now, username))
                
                # Kunlik statistika (unfollow)
                date_str = now.date().isoformat()
                cursor.execute("""
                    INSERT INTO daily_stats (date, follow_count, unfollow_count)
                    VALUES (?, 0, 1)
                    ON CONFLICT(date) DO UPDATE SET unfollow_count = unfollow_count + 1
                """, (date_str,))
                
            else:
                cursor.execute("UPDATE users SET status = ? WHERE username = ?", (status, username))
                
            conn.commit()
    except Exception as e:
        logger.error(f"❌ DB Update status error: {e}")

def get_waiting_users():
    """24 soat o'tganlarni olish uchun ro'yxat"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE status = 'waiting'")
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"❌ DB Get waiting users error: {e}")
        return []

def get_today_stats():
    """Bugungi statistika"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            date_str = datetime.now().date().isoformat()
            cursor.execute("SELECT * FROM daily_stats WHERE date = ?", (date_str,))
            row = cursor.fetchone()
            if row:
                return row['follow_count'], row['unfollow_count']
            return 0, 0
    except Exception as e:
        logger.error(f"❌ DB Get stats error: {e}")
        return 0, 0

def get_total_stats():
    """Umumiy statistika"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as backed FROM users WHERE status = 'followed_back'")
            backed = cursor.fetchone()['backed']
            
            cursor.execute("SELECT COUNT(*) as waiting FROM users WHERE status = 'waiting'")
            waiting = cursor.fetchone()['waiting']
            
            return total, waiting, backed
    except Exception as e:
        logger.error(f"❌ DB Get total stats error: {e}")
        return 0, 0, 0

def get_all_users_by_status(status: str = None):
    """Statusga ko'ra userlarni olish"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT username, status, followed_at FROM users WHERE status = ? ORDER BY followed_at DESC", (status,))
            else:
                cursor.execute("SELECT username, status, followed_at FROM users ORDER BY followed_at DESC")
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"❌ DB Get all users error: {e}")
        return []

def get_non_followers():
    """Follow qilmagan userlar (waiting status, 24 soat o'tgan)"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT username, followed_at 
                FROM users 
                WHERE status = 'waiting' 
                ORDER BY followed_at ASC
            """)
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"❌ DB Get non-followers error: {e}")
        return []

def set_config(key: str, value: str):
    """Config qiymatini saqlash"""
    try:
        with get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()
    except Exception as e:
        logger.error(f"❌ DB Set config error: {e}")

def get_config(key: str, default=None):
    """Config qiymatini olish"""
    try:
        with get_connection() as conn:
            cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
            result = cursor.fetchone()
            return result['value'] if result else default
    except Exception as e:
        logger.error(f"❌ DB Get config error: {e}")
        return default

