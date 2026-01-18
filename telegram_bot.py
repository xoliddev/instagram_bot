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

def load_targets() -> list:
    """Targetlar ro'yxatini yuklash"""
    if TARGETS_FILE.exists():
        try:
            with open(TARGETS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    # Boshlang'ich target
    default = [os.getenv("TARGET_ACCOUNT", "muhibulloh_")]
    save_targets(default)
    return default

def save_targets(targets: list):
    """Targetlarni saqlash"""
    with open(TARGETS_FILE, 'w') as f:
        json.dump(targets, f)

def get_random_target() -> str:
    """Tasodifiy target olish"""
    import random
    targets = load_targets()
    return random.choice(targets) if targets else "muhibulloh_"

# ============ BOT STATE ============
class BotState:
    is_running = False
    current_cycle = None
    last_action = None
    instagram_bot = None

state = BotState()

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
    
    text = """
🤖 <b>Instagram Bot Controller</b>

<b>Buyruqlar:</b>
📊 /stats - Statistika
▶️ /follow [son] - Follow sikli
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

<b>Holat:</b> """ + ("🟢 Ishlayapti" if state.is_running else "🔴 Kutish rejimi")
    
    await message.answer(text)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    today_follow, today_unfollow = database.get_today_stats()
    total, waiting, backed = database.get_total_stats()
    targets = load_targets()
    
    text = f"""
📊 <b>Statistika</b>

<b>Bugun:</b>
├ ➕ Follow: {today_follow}
└ ➖ Unfollow: {today_unfollow}

<b>Umumiy:</b>
├ 👥 Jami: {total}
├ ⏳ Kutilmoqda: {waiting}
└ ✅ Follow back: {backed}

<b>Targetlar:</b> {len(targets)} ta
└ {', '.join(['@'+t for t in targets[:5]])}{'...' if len(targets) > 5 else ''}

<b>Bot holati:</b> {"🟢 Ishlayapti" if state.is_running else "🔴 Kutish"}
"""
    await message.answer(text)

@router.message(Command("logs"))
async def cmd_logs(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    if not LOG_FILE.exists():
        await message.answer("📜 Log fayl topilmadi.")
        return
    
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()[-20:]  # Oxirgi 20 qator
        
        text = "📜 <b>Oxirgi loglar:</b>\n\n<code>" + "".join(lines)[-3500:] + "</code>"
        await message.answer(text)
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@router.message(Command("targets"))
async def cmd_targets(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    targets = load_targets()
    if not targets:
        await message.answer("🎯 Targetlar ro'yxati bo'sh.")
        return
    
    text = "🎯 <b>Targetlar:</b>\n\n"
    for i, t in enumerate(targets, 1):
        text += f"{i}. @{t}\n"
    
    text += f"\n<i>Har sikl boshida tasodifiy tanlanadi</i>"
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
    
    targets = load_targets()
    if username in targets:
        await message.answer(f"⚠️ @{username} allaqachon ro'yxatda.")
        return
    
    targets.append(username)
    save_targets(targets)
    await message.answer(f"✅ @{username} qo'shildi!\n\n🎯 Jami: {len(targets)} ta target")

@router.message(Command("remove_target"))
async def cmd_remove_target(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Foydalanish: /remove_target @username")
        return
    
    username = args[1].strip().lstrip("@")
    targets = load_targets()
    
    if username not in targets:
        await message.answer(f"⚠️ @{username} ro'yxatda yo'q.")
        return
    
    if len(targets) <= 1:
        await message.answer("❌ Kamida 1 ta target bo'lishi kerak!")
        return
    
    targets.remove(username)
    save_targets(targets)
    await message.answer(f"✅ @{username} o'chirildi!\n\n🎯 Qoldi: {len(targets)} ta target")

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
    
    if state.is_running:
        await message.answer("⚠️ Bot allaqachon ishlayapti. Kuting...")
        return
    
    args = message.text.split()
    count = 20
    if len(args) > 1 and args[1].isdigit():
        count = min(int(args[1]), 50)  # Max 50
    
    target = get_random_target()
    await message.answer(f"▶️ Follow sikli boshlanmoqda...\n\n🎯 Target: @{target}\n👥 Limit: {count}")
    
    # Signal Instagram bot to start
    state.current_cycle = "follow"
    state.last_action = datetime.now()
    # TODO: Actual integration with bot_browser

@router.message(Command("unfollow"))
async def cmd_unfollow(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    if state.is_running:
        await message.answer("⚠️ Bot allaqachon ishlayapti.")
        return
    
    await message.answer("⏹️ Unfollow sikli boshlanmoqda...")
    state.current_cycle = "unfollow"

@router.message(Command("cleanup"))
async def cmd_cleanup(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    await message.answer("🧹 Following tozalash sikli boshlanmoqda...\n\n<i>Sizga follow qilmaganlar unfollow qilinadi.</i>")
    state.current_cycle = "cleanup"

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
