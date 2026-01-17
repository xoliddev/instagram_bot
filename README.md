# 📸 Instagram Follow/Unfollow Bot

Avtomatik follow, 24 soatlik tekshirish va unfollow qiluvchi bot.

## 🚀 Imkoniyatlar

- ✅ Avtomatik yangi odamlarni follow qilish (hashtag yoki akkaunt bo'yicha)
- ✅ 24 soatdan keyin follow qaytarganlarni tekshirish
- ✅ Qaytarmaganlarni avtomatik unfollow qilish
- ✅ Xavfsiz vaqt oralig'lari (60-180 sekund)
- ✅ Kunlik limitlar (100 follow/unfollow)
- ✅ Session saqlash (har safar login qilish shart emas)
- ✅ 2FA (ikki bosqichli autentifikatsiya) qo'llab-quvvatlash
- ✅ Batafsil statistika

## 📋 O'rnatish

### 1. Python o'rnating
Python 3.8+ versiyasi kerak: https://python.org/downloads

### 2. Loyihani oching
```bash
cd instagram-bot
```

### 3. Kutubxonalarni o'rnating
```bash
pip install -r requirements.txt
```

### 4. Sozlamalarni kiriting
`config.py` faylini oching va quyidagilarni o'zgartiring:

```python
# Instagram login
INSTAGRAM_USERNAME = "sizning_username"
INSTAGRAM_PASSWORD = "sizning_parol"

# Target (kimlarni follow qilish)
TARGET_ACCOUNT = "popular_account"  # Bu akkauntning followerlarini follow qilasiz
```

### 5. Botni ishga tushiring
```bash
python bot.py
```

## 🎮 Foydalanish

Botni ishga tushirgandan keyin menyu chiqadi:

| Buyruq | Vazifasi |
|--------|----------|
| 1 | Follow siklini boshlash (bir marta) |
| 2 | Unfollow siklini boshlash (24 soat o'tganlarni tekshirish) |
| 3 | Avtomatik 24/7 rejim |
| 4 | Statistikani ko'rish |
| 5 | Chiqish |

## ⚙️ Sozlamalar

`config.py` faylida quyidagilarni o'zgartirishingiz mumkin:

| Sozlama | Tavsif | Default |
|---------|--------|---------|
| `FOLLOW_DELAY_MIN` | Follow orasidagi min vaqt (sekund) | 60 |
| `FOLLOW_DELAY_MAX` | Follow orasidagi max vaqt (sekund) | 180 |
| `DAILY_FOLLOW_LIMIT` | Kunlik follow limiti | 100 |
| `DAILY_UNFOLLOW_LIMIT` | Kunlik unfollow limiti | 100 |
| `CHECK_INTERVAL` | Tekshirish oralig'i (sekund) | 86400 (24 soat) |

## ⚠️ Muhim Ogohlantirishlar

1. **Akkaunt xavfsizligi**: Bu bot Instagram qoidalariga zid. Akkauntingiz vaqtincha yoki butunlay bloklanishi mumkin.

2. **Limitlarni hurmat qiling**: Kunlik 100 dan ortiq follow/unfollow qilmang.

3. **Proxy ishlatish**: Ko'p akkaunt bilan ishlasangiz, proxy ishlatish tavsiya etiladi.

4. **Dam olish**: Botni 24/7 ishlatmang, orada dam bering.

## 📁 Fayllar

```
instagram-bot/
├── bot.py              # Asosiy bot kodi
├── config.py           # Sozlamalar
├── requirements.txt    # Python kutubxonalar
├── session.json        # Instagram session (avtomatik yaratiladi)
├── following_data.json # Follow ma'lumotlari (avtomatik yaratiladi)
├── bot.log            # Log fayli (avtomatik yaratiladi)
└── README.md          # Qo'llanma
```

## 🔧 Muammolar va Yechimlar

### "Challenge Required" xatosi
Instagram sizdan qo'shimcha tasdiqlash so'ramoqda. Telefon ilovasidan tasdiqlang.

### "Rate Limit" xatosi
Juda ko'p so'rov yuborilgan. Bot avtomatik 10 daqiqa kutadi.

### "2FA Required" xatosi
SMS yoki Authenticator kodini kiriting.

## 📞 Aloqa

Savollar bo'lsa, murojaat qiling!

---
⚡ Made with Python & Instagrapi
