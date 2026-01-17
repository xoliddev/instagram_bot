import os# Instagram Bot Configuration

# Foydalanuvchi ma'lumotlari

# =============================================
# 🔐 INSTAGRAM LOGIN MA'LUMOTLARI
# =============================================
from dotenv import load_dotenv
load_dotenv()

INSTAGRAM_USERNAME = os.environ.get("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.environ.get("INSTAGRAM_PASSWORD")

# =============================================
# 🎯 TARGET MANBA (Kimlarni follow qilish)
# =============================================
TARGET_ACCOUNT = os.environ.get("TARGET_ACCOUNT", "muhibulloh_")  # Default bo'lishi mumkin
TARGET_HASHTAG = ""

# ...
NIGHT_REST_START = 0   # Soat 00:00
NIGHT_REST_END = 7     # Soat 07:00

# =============================================
# ⏱️ INSONIY VAQT ORALIG'I (sekundda)
# =============================================
# Follow orasidagi vaqt (real odam kabi - 2-5 daqiqa)
FOLLOW_DELAY_MIN = 120   # 2 daqiqa
FOLLOW_DELAY_MAX = 300   # 5 daqiqa

# Unfollow orasidagi vaqt (real odam kabi - 2-5 daqiqa)
UNFOLLOW_DELAY_MIN = 120  # 2 daqiqa
UNFOLLOW_DELAY_MAX = 300  # 5 daqiqa

# Tekshirish orasidagi vaqt (24 soat = 86400 sekund)
CHECK_INTERVAL = 86400  # 24 soat

# =============================================
# 📊 LIMITLAR (Kunlik - xavfsiz miqdor)
# =============================================
DAILY_FOLLOW_LIMIT = 80     # Kuniga maksimum follow
DAILY_UNFOLLOW_LIMIT = 80   # Kuniga maksimum unfollow

# =============================================
# 📁 FAYL NOMLARI
# =============================================
SESSION_FILE = "session.json"           # Session saqlash
FOLLOWING_DB = "following_data.json"    # Follow qilinganlar ro'yxati (baza)
LOG_FILE = "bot.log"                    # Log fayli

# =============================================
# 🖥️ SERVER SOZLAMALARI
# =============================================
import os

# ...

# =============================================
# 🖥️ SERVER SOZLAMALARI
# =============================================
# Agar serverda bo'lsa (HEADLESS env vari bor bo'lsa), o'shani oladi. Yo'qsa False.
HEADLESS = os.environ.get("HEADLESS", "False").lower() == "true"
