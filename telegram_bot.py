"""
Telegram Bot Controller for Instagram Bot
Admin panel orqali bot boshqarish
"""
import os
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import database

load_dotenv()

# ============ CONFIG ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
INITIAL_ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip().isdigit()]

ADMINS_FILE = Path("admins.json")
TARGETS_FILE = Path("targets.json")
LOG_FILE = Path("bot.log")
DB_FILE = Path("bot.db")

# ============ DATA MANAGEMENT ============
def load_admins() -> list:
    """Adminlar ro'yxatini yuklash"""
    if ADMINS_FILE.exists():
        try:
            with open(ADMINS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    # Boshlang'ich adminlar
    save_admins(INITIAL_ADMIN_IDS)
    return INITIAL_ADMIN_IDS

def save_admins(admins: list):
    """Adminlarni saqlash"""
    with open(ADMINS_FILE, 'w') as f:
        json.dump(admins, f)

def migrate_targets_to_db():
    """Eski JSON targetlarni bazaga ko'chirish (bir martalik)"""
    if TARGETS_FILE.exists():
        try:
            with open(TARGETS_FILE, 'r') as f:
                targets = json.load(f)
            for t in targets:
                database.add_target(t)
            TARGETS_FILE.unlink()  # Faylni o'chirish
            logger.info(f"✅ {len(targets)} ta target bazaga ko'chirildi")
        except Exception as e:
            logger.warning(f"⚠️ Target migratsiya: {e}")

# ============ BOT STATE ============


# ============ LOGGING ============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ BOT SETUP ============
bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
router = Router()

# ============ MIDDLEWARE ============
def is_admin(user_id: int) -> bool:
    """Admin tekshirish"""
    admins = load_admins()
    return user_id in admins

# ============ HANDLERS ============
@router.message(CommandStart())
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Sizda ruxsat yo'q.")
        return
    
    args = message.text.split()
    
    text = f"""
🤖 <b>Instagram Bot Controller</b>

<b>Buyruqlar:</b>
📊 /stats - Statistika
▶️ /follow [son] - Follow sikli (Direct)
⏹️ /unfollow - Unfollow sikli
🧹 /cleanup - Following tozalash
👎 /non_followers - Follow qaytarmaganlar
✅ /followed_back - Follow qaytarganlar
📜 /logs - Oxirgi loglar
🎯 /targets - Targetlar ro'yxati

<b>Admin:</b>
➕ /add_admin [id]
➖ /remove_admin [id]

<b>Target:</b>
➕ /add_target [@username]
➖ /remove_target [@username]

<b>Holat:</b> 🟢 Ishlayapti (Cycle: {database.get_config('current_cycle', 'auto')})"""
    
    await message.answer(text)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    today_follow, today_unfollow = database.get_today_stats()
    status_counts = database.get_status_counts()
    target_count = database.get_target_count()
    
    text = f"""
📊 <b>Statistika</b>

<b>Bugun:</b>
├ ➕ Follow: {today_follow}
└ ➖ Unfollow: {today_unfollow}

<b>Bazadagi userlar:</b> {status_counts['total']} ta
├ 📥 Pending: {status_counts['pending']}
├ ⏳ Waiting: {status_counts['waiting']}
├ ✅ Followed Back: {status_counts['followed_back']}
├ 🚫 Unfollowed: {status_counts['unfollowed']}
└ ❌ Blocked: {status_counts['blocked']}

<b>🎯 Targetlar:</b> {target_count} ta
<b>Sikl:</b> {database.get_config('current_cycle', 'auto')}
"""
    await message.answer(text)

@router.message(Command("logs"))
async def cmd_logs(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    # Log fayllarni tekshirish
    log_files = [Path("bot.log"), Path("/tmp/bot.log"), Path("logs/bot.log")]
    log_content = None
    
    for log_file in log_files:
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[-20:]
                log_content = "".join(lines)
                break
            except:
                continue
    
    if log_content:
        text = "📜 <b>Oxirgi loglar:</b>\n\n<code>" + log_content[-3500:] + "</code>"
    else:
        text = """📜 <b>Log fayl topilmadi</b>

<i>Loglarni ko'rish uchun:</i>
1. Koyeb Dashboard → Console
2. Runtime Logs qismida ko'ring

<i>Yoki /stats buyrug'i bilan statistikani ko'ring.</i>"""
    
    await message.answer(text)

@router.message(Command("targets"))
async def cmd_targets(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    targets = database.get_all_targets()
    if not targets:
        await message.answer("🎯 Targetlar ro'yxati bo'sh.\n\nQo'shish: /add_target @username")
        return
    
    text = "🎯 <b>Targetlar:</b>\n\n"
    for i, t in enumerate(targets, 1):
        text += f"{i}. @{t}\n"
    
    text += f"\n<i>Pending bo'sh bo'lganda random tanlanadi</i>"
    await message.answer(text)

@router.message(Command("add_target"))
async def cmd_add_target(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Foydalanish: /add_target @username")
        return
    
    username = args[1].strip().lstrip("@")
    if not username:
        await message.answer("❌ Username kiriting.")
        return
    
    targets = database.get_all_targets()
    if username in targets:
        await message.answer(f"⚠️ @{username} allaqachon ro'yxatda.")
        return
    
    database.add_target(username)
    await message.answer(f"✅ @{username} qo'shildi!\n\n🎯 Jami: {len(targets) + 1} ta target")

@router.message(Command("remove_target"))
async def cmd_remove_target(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Foydalanish: /remove_target @username")
        return
    
    username = args[1].strip().lstrip("@")
    targets = database.get_all_targets()
    
    if username not in targets:
        await message.answer(f"⚠️ @{username} ro'yxatda yo'q.")
        return
    
    database.remove_target(username)
    await message.answer(f"✅ @{username} o'chirildi!\n\n🎯 Qoldi: {len(targets) - 1} ta target")

@router.message(Command("add_admin"))
async def cmd_add_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("❌ Foydalanish: /add_admin 123456789")
        return
    
    new_admin = int(args[1].strip())
    admins = load_admins()
    
    if new_admin in admins:
        await message.answer("⚠️ Bu admin allaqachon ro'yxatda.")
        return
    
    admins.append(new_admin)
    save_admins(admins)
    await message.answer(f"✅ Admin qo'shildi: {new_admin}\n\n👥 Jami: {len(admins)} ta admin")

@router.message(Command("remove_admin"))
async def cmd_remove_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("❌ Foydalanish: /remove_admin 123456789")
        return
    
    admin_id = int(args[1].strip())
    admins = load_admins()
    
    if admin_id not in admins:
        await message.answer("⚠️ Bu admin ro'yxatda yo'q.")
        return
    
    if len(admins) <= 1:
        await message.answer("❌ Kamida 1 ta admin bo'lishi kerak!")
        return
    
    if admin_id == message.from_user.id:
        await message.answer("❌ O'zingizni o'chira olmaysiz!")
        return
    
    admins.remove(admin_id)
    save_admins(admins)
    await message.answer(f"✅ Admin o'chirildi: {admin_id}")

@router.message(Command("follow"))
async def cmd_follow(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    if database.get_config("current_cycle") == "follow":
        await message.answer("⚠️ Bot allaqachon follow rejimida. Kuting...")
        return
    
    args = message.text.split()
    count = 20
    if len(args) > 1 and args[1].isdigit():
        count = min(int(args[1]), 50)  # Max 50
    
    target = database.get_random_target()
    if not target:
        await message.answer("⚠️ Target yo'q! Avval /add_target @username bilan qo'shing.")
        return
        
    await message.answer(f"▶️ Follow sikli boshlanmoqda...\n\n🎯 Target: @{target}\n👥 Limit: {count}")
    
    # Signal Instagram bot to start
    database.set_config("current_cycle", "follow")
    database.set_config("follow_target", target)
    database.set_config("follow_count", str(count))

@router.message(Command("unfollow"))
async def cmd_unfollow(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    if database.get_config("current_cycle") == "cleanup":
        await message.answer("⚠️ Bot allaqachon cleanup rejimida.")
        return
    
    await message.answer("ℹ️ Unfollow avtomatik rejimda ishlaydi.\n\nBot har 24 soatda follow qaytarmaganlarni o'zi tozalaydi.\n\n🧹 Majburiy tozalash (Smart Cleanup) uchun: /cleanup")
    database.set_config("current_cycle", "auto")

@router.message(Command("cleanup"))
async def cmd_cleanup(message: Message):    
    if not is_admin(message.from_user.id):
        return
    
    await message.answer("🧹 <b>Smart Cleanup boshlanmoqda...</b>\n\n1. Followerlar va Followinglar real vaqtda solishtiriladi\n2. Follow qaytarmaganlar tekshiriladi\n3. 'Follows You' bo'lmasa -> Unfollow qilinadi\n\n<i>Bu jarayon biroz vaqt oladi!</i>")
    database.set_config("current_cycle", "cleanup")
    database.set_config("strict_mode", "false")

@router.message(Command("stories"))
async def cmd_stories(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    await message.answer("🍿 <b>Story tomosha qilish boshlanmoqda...</b>\n\nBot barcha storylarni birma-bir ko'rib, random like bosib chiqadi.\nStorylar tugagach, avtomatik to'xtaydi.")
    database.set_config("current_cycle", "stories")

@router.message(Command("collect"))
async def cmd_collect(message: Message):
    """Followerlarni bazaga to'plash"""
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Foydalanish: /collect @username [son]\n\nMisol: /collect @muhibulloh_ 5000")
        return
    
    target = args[1].strip().lstrip("@")
    count = 1000  # Default
    if len(args) > 2 and args[2].isdigit():
        count = min(int(args[2]), 10000)  # Max 10k
    
    pending_count = database.get_pending_count()
    
    await message.answer(f"""📥 <b>Follower to'plash boshlanmoqda...</b>

🎯 Target: @{target}
📊 Maqsad: {count} ta
📋 Hozirgi pending: {pending_count} ta

<i>Bu jarayon bir necha daqiqa olishi mumkin...</i>
<i>Progress Koyeb loglarida ko'rinadi.</i>""")
    
    database.set_config("current_cycle", "collect")
    database.set_config("collect_target", target)
    database.set_config("collect_count", count)

@router.message(Command("pending"))
async def cmd_pending(message: Message):
    """Pending userlar (to'plangan, hali follow qilinmagan)"""
    if not is_admin(message.from_user.id):
        return
    
    pending_count = database.get_pending_count()
    pending_users = database.get_pending_users(10)  # Faqat 10 ta ko'rsatish
    
    if pending_count == 0:
        await message.answer("📋 Pending userlar yo'q.\n\nYangi to'plash uchun: /collect @username 1000")
        return
    
    text = f"📋 <b>Pending userlar:</b> {pending_count} ta\n\n"
    
    for i, username in enumerate(pending_users, 1):
        text += f"{i}. @{username}\n"
    
    if pending_count > 10:
        text += f"\n<i>... va yana {pending_count - 10} ta</i>"
    
    text += "\n\n💡 <i>Bu userlar keyingi follow siklda follow qilinadi.</i>"
    
    await message.answer(text)

@router.message(Command("non_followers"))
async def cmd_non_followers(message: Message):
    """Sizga follow qilmaganlar ro'yxati"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer("🔍 Bazadan ma'lumotlar olinmoqda...")
    
    # Waiting statusdagi userlar (follow qaytarmagan)
    waiting_users = database.get_non_followers()
    
    if not waiting_users:
        await message.answer("✅ Hozircha follow qaytarmagan foydalanuvchi yo'q yoki baza bo'sh.")
        return
    
    # Ro'yxat tuzish
    text = f"👎 <b>Follow qaytarmaganlar:</b> {len(waiting_users)} ta\n\n"
    
    for i, user in enumerate(waiting_users[:30], 1):  # Max 30 ta ko'rsatish
        username = user['username']
        followed_at = user['followed_at']
        text += f"{i}. @{username}\n"
    
    if len(waiting_users) > 30:
        text += f"\n<i>... va yana {len(waiting_users) - 30} ta</i>"
    
    text += "\n\n💡 <i>Ularni unfollow qilish uchun: /cleanup</i>"
    
    await message.answer(text)

@router.message(Command("followed_back"))
async def cmd_followed_back(message: Message):
    """Follow qaytarganlar ro'yxati"""
    if not is_admin(message.from_user.id):
        return
    
    users = database.get_all_users_by_status('followed_back')
    
    if not users:
        await message.answer("📭 Hozircha follow qaytargan foydalanuvchi yo'q.")
        return
    
    text = f"✅ <b>Follow qaytarganlar:</b> {len(users)} ta\n\n"
    
    for i, user in enumerate(users[:30], 1):
        username = user['username']
        text += f"{i}. @{username}\n"
    
    if len(users) > 30:
        text += f"\n<i>... va yana {len(users) - 30} ta</i>"
    
    await message.answer(text)

@router.message(Command("backup"))
async def cmd_backup(message: Message):
    """Bazani GitHub Gist ga saqlash"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer("💾 Backup boshlanmoqda...")
    
    try:
        import backup
        if backup.backup_to_gist():
            data = backup.export_db_to_json()
            user_count = len(data.get("users", []))
            await message.answer(f"✅ Backup muvaffaqiyatli!\n\n👥 {user_count} ta user saqlandi\n\n<i>Gist da saqlandi</i>")
        else:
            await message.answer("❌ Backup xatosi!\n\n<i>GITHUB_TOKEN yoki GIST_ID ni tekshiring</i>")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@router.message(Command("restore"))
async def cmd_restore(message: Message):
    """Bazani GitHub Gist dan qayta yuklash"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer("📥 Restore boshlanmoqda...")
    
    try:
        import backup
        if backup.restore_from_gist():
            await message.answer("✅ Restore muvaffaqiyatli!\n\n<i>Baza yangilandi</i>")
        else:
            await message.answer("❌ Restore xatosi!\n\n<i>GITHUB_TOKEN yoki GIST_ID ni tekshiring</i>")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

# ============ NOTIFICATION HELPER ============
async def notify_admins(text: str):
    """Barcha adminlarga xabar yuborish"""
    admins = load_admins()
    for admin_id in admins:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

# ============ MAIN ============
async def main():
    """Telegram botni ishga tushirish"""
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN topilmadi!")
        return
    
    dp.include_router(router)
    
    logger.info("🤖 Telegram bot ishga tushmoqda...")
    
    # Adminlarga xabar
    await notify_admins("🟢 <b>Bot ishga tushdi!</b>\n\n/start - Boshqaruv paneli")
    
    await dp.start_polling(bot)

def run_telegram_bot():
    """Sync wrapper for running telegram bot"""
    asyncio.run(main())

if __name__ == "__main__":
    run_telegram_bot()
