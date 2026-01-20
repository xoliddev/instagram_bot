"""
Database Backup System - GitHub Gist
Bazani GitHub Gist da saqlash va qayta yuklash
"""
import os
import json
import base64
import sqlite3
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Config
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GIST_ID = os.getenv("GIST_ID", "")  # Mavjud gist ID (bo'sh bo'lsa yangi yaratiladi)
DB_FILE = Path("bot.db")
BACKUP_FILE = "instagram_bot_backup.json"

def export_db_to_json() -> dict:
    """SQLite bazani JSON formatga o'tkazish"""
    if not DB_FILE.exists():
        return {"users": [], "daily_stats": []}
    
    try:
        conn = sqlite3.connect(str(DB_FILE))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Users jadvali
        cursor.execute("SELECT * FROM users")
        users = [dict(row) for row in cursor.fetchall()]
        
        # Daily stats jadvali
        cursor.execute("SELECT * FROM daily_stats")
        daily_stats = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "users": users,
            "daily_stats": daily_stats,
            "exported_at": str(__import__('datetime').datetime.now())
        }
    except Exception as e:
        logger.error(f"❌ Export error: {e}")
        return {"users": [], "daily_stats": []}

def import_json_to_db(data: dict) -> bool:
    """JSON dan SQLite bazaga import"""
    try:
        import database
        database.init_db()
        
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()
        
        # Users import
        for user in data.get("users", []):
            cursor.execute("""
                INSERT OR REPLACE INTO users (username, status, followed_at, unfollowed_at, checked, fail_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user.get("username"),
                user.get("status"),
                user.get("followed_at"),
                user.get("unfollowed_at"),
                user.get("checked", 0),
                user.get("fail_count", 0)
            ))
        
        # Daily stats import
        for stat in data.get("daily_stats", []):
            cursor.execute("""
                INSERT OR REPLACE INTO daily_stats (date, follow_count, unfollow_count)
                VALUES (?, ?, ?)
            """, (
                stat.get("date"),
                stat.get("follow_count", 0),
                stat.get("unfollow_count", 0)
            ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Import muvaffaqiyatli: {len(data.get('users', []))} user, {len(data.get('daily_stats', []))} stat")
        return True
        
    except Exception as e:
        logger.error(f"❌ Import error: {e}")
        return False

def backup_to_gist() -> bool:
    """Bazani GitHub Gist ga yuklash"""
    if not GITHUB_TOKEN:
        logger.warning("⚠️ GITHUB_TOKEN yo'q, backup o'tkazib yuborildi")
        return False
    
    data = export_db_to_json()
    content = json.dumps(data, indent=2, ensure_ascii=False)
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        if GIST_ID:
            # Mavjud gistni yangilash
            url = f"https://api.github.com/gists/{GIST_ID}"
            response = requests.patch(url, headers=headers, json={
                "files": {
                    BACKUP_FILE: {"content": content}
                }
            })
        else:
            # Yangi gist yaratish
            url = "https://api.github.com/gists"
            response = requests.post(url, headers=headers, json={
                "description": "Instagram Bot Database Backup",
                "public": False,
                "files": {
                    BACKUP_FILE: {"content": content}
                }
            })
            
            if response.status_code == 201:
                new_gist_id = response.json().get("id")
                logger.info(f"✅ Yangi Gist yaratildi: {new_gist_id}")
                logger.info(f"⚠️ GIST_ID={new_gist_id} ni .env ga qo'shing!")
        
        if response.status_code in [200, 201]:
            user_count = len(data.get("users", []))
            logger.info(f"✅ Backup muvaffaqiyatli: {user_count} ta user saqlandi")
            return True
        else:
            logger.error(f"❌ Gist xatosi: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Backup xatosi: {e}")
        return False

def restore_from_gist() -> bool:
    """GitHub Gist dan bazani qayta yuklash"""
    if not GITHUB_TOKEN or not GIST_ID:
        logger.warning("⚠️ GITHUB_TOKEN yoki GIST_ID yo'q, restore o'tkazib yuborildi")
        return False
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"❌ Gist olishda xato: {response.status_code}")
            return False
        
        gist_data = response.json()
        files = gist_data.get("files", {})
        
        if BACKUP_FILE not in files:
            logger.warning(f"⚠️ {BACKUP_FILE} gistda topilmadi")
            return False
        
        content = files[BACKUP_FILE].get("content", "{}")
        data = json.loads(content)
        
        return import_json_to_db(data)
        
    except Exception as e:
        logger.error(f"❌ Restore xatosi: {e}")
        return False

def auto_restore_if_empty():
    """Agar lokal baza bo'sh bo'lsa, gistdan qayta yuklash"""
    try:
        if not DB_FILE.exists():
            logger.info("📥 Lokal baza topilmadi, Gist dan yuklanmoqda...")
            return restore_from_gist()
        
        # Baza bor, lekin bo'shmi?
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        conn.close()
        
        if count == 0:
            logger.info("📥 Lokal baza bo'sh, Gist dan yuklanmoqda...")
            return restore_from_gist()
        
        # Agar baza bo'sh bo'lmasa ham, Gist dagi ma'lumotlarni merge qilishimiz kerak
        logger.info(f"✅ Lokal bazada {count} ta user mavjud. Gist bilan senxronizatsiya qilinmoqda...")
        return restore_from_gist()
        
    except Exception as e:
        logger.error(f"❌ Auto-restore xatosi: {e}")
        return restore_from_gist()
        
    except Exception as e:
        logger.error(f"❌ Auto-restore xatosi: {e}")
        return restore_from_gist()
