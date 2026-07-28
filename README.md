# ATLON GROUP — Telegram bot

Yoshlar loyihasi uchun Telegram bot: kanalga obuna nazorati, loyiha haqida
ma’lumot, shaharlar bo‘yicha tadbirlar, volontyor arizalarini yig‘ish, ularni
shahar guruhlariga yuborish va shahar bo‘yicha bildirishnomalar.

## Imkoniyatlar

- **Obuna nazorati** — foydalanuvchi avval kanalga obuna bo‘lishi shart.
- **Asosiy menyu** — *Atlon Group haqida*, *Tadbirlar*, *Volontyor bo‘lish*.
- **Tadbirlar** — shahar tanlanganda shahar tugmalari yo‘qoladi va tadbirlar
  bittalab ko‘rsatiladi (*⬅️ Avvalgisi* / *Keyingisi ➡️*), har birining tagida
  ro‘yxatdan o‘tish tugmasi bilan.
- **Tadbirga ro‘yxatdan o‘tish** — ism-familiya, yosh, telefon, to‘lov cheki
  (**faqat rasm ko‘rinishida**). So‘ng admin chekni tasdiqlaydi yoki rad etadi;
  tasdiqlangach foydalanuvchiga tabrik va tadbir ma’lumotlari yuboriladi.
- **Volontyor arizasi** — shahar, ism-familiya, yosh, telefon (kontakt tugmasi),
  qiziqishlar, bio.
- **Saqlash** — ma’lumotlar bazasi (Postgres/SQLite) + Excel export (`/export`).
- **Guruhlarga yuborish** — ariza tanlangan shaharning guruhiga yuboriladi.
- **Bildirishnoma** — yangi tadbir qo‘shilganda, o‘sha shaharni tanlagan
  foydalanuvchilarga xabar boradi.
- **Admin panel** — `/addevent`, `/broadcast`, `/export`, `/stats`.

## Texnologiya

Python 3.11 · `python-telegram-bot` v21 (polling) · SQLAlchemy ·
Postgres (Railway) yoki SQLite (lokal) · openpyxl.

## 1) Botni yaratish (@BotFather)

1. Telegramda [@BotFather](https://t.me/BotFather) ga yozing → `/newbot`.
2. Nom va username bering → sizga **token** beriladi.
3. Kanalingizga botni **admin** qilib qo‘shing (obunani tekshirish uchun shart).
4. Har bir shahar guruhiga botni qo‘shing (arizalar shu yerga tushadi).

## 2) Muhit o‘zgaruvchilari (environment variables)

`.env.example` faylidan nusxa oling. Asosiylari:

| Variable | Tavsif |
|---|---|
| `BOT_TOKEN` | @BotFather bergan token (**majburiy**) |
| `CHANNEL_USERNAME` | Obuna kanali, masalan `@atlongroup` |
| `CHANNEL_URL` | Ixtiyoriy — tugmadagi havola |
| `ADMIN_IDS` | Admin Telegram ID lari, vergul bilan (`@userinfobot`) |
| `GROUP_*` (14 ta) | Har viloyat guruhining chat ID si (`-100…`) — to‘liq ro‘yxat `.env.example` da |
| `DATABASE_URL` | Postgres URL (Railwayda avtomatik) |

> Guruh chat ID sini bilish uchun botni guruhga qo‘shing, guruhga bir xabar
> yozing va logdan `chat_id` ni ko‘ring, yoki `@getidsbot` dan foydalaning.

## 3) Lokal ishga tushirish

```bash
pip install -r requirements.txt
cp .env.example .env      # va qiymatlarni to‘ldiring
python bot.py
```

## 4) Railwayda deploy

1. Bu repozitoriyni GitHubga yuklang.
2. [Railway](https://railway.app) da **New Project → Deploy from GitHub repo**.
3. **Variables** bo‘limiga yuqoridagi o‘zgaruvchilarni qo‘shing.
4. (Tavsiya) **New → Database → PostgreSQL** qo‘shing — `DATABASE_URL`
   avtomatik ulanadi va ma’lumotlar deploylar orasida saqlanadi.
5. Railway `Procfile` (`worker: python bot.py`) orqali botni ishga tushiradi.

> SQLite (default) faylida ma’lumotlar redeploy paytida yo‘qoladi — shu sabab
> productionда Postgres ishlatilsin.

## Admin buyruqlari

| Buyruq | Vazifa |
|---|---|
| `/admin` | Admin yordam menyusi |
| `/addevent` | Tadbir qo‘shish: shahar, nom, sana, tavsif, **to‘lov summasi** (+ bildirishnoma) |
| `/events` | Tadbirlarni tahrirlash yoki o‘chirish |
| `/pending` | Tekshirilmagan tadbir arizalarini qayta ko‘rish |
| `/broadcast` | Hammaga yoki shahar bo‘yicha xabar |
| `/export` | Volontyor + tadbir arizalarini Excel qilib yuklab olish |
| `/stats` | Statistika |
| `/id` | Joriy chat ID sini bilish (guruh sozlash uchun) |
| `/bekor` | Jarayonni bekor qilish |

### Tadbir arizasini tasdiqlash

Foydalanuvchi chek rasmini yuborgach, ariza `ADMIN_IDS` dagi barcha adminlarga
chek rasmi bilan birga yuboriladi va tagida **✅ Tasdiqlash** / **❌ Rad etish**
tugmalari chiqadi. Tasdiqlangach foydalanuvchi quyidagi xabarni oladi:

```
🎉 Tabriklaymiz!
Sizning Atlon Group tadbiriga yuborgan arizangiz muvaffaqiyatli tasdiqlandi. ✅

🎉 Debat
🗓 7-may, 17:00
📍 Xorazm

ℹ️ Aniq lokatsiya telegram kanalga yuboriladi.
```

Ikki admin bir vaqtda bosib yuborsa, ikkinchisiga «allaqachon tasdiqlangan»
deb ko‘rsatiladi va foydalanuvchiga takroriy xabar bormaydi.

## Loyiha tuzilishi

```
bot.py        — kirish nuqtasi, asosiy user flow, volontyor arizasi
admin.py      — admin panel (tadbir, broadcast, export, stats)
config.py     — muhit o‘zgaruvchilari, shaharlar, guruh ID lari
texts.py      — barcha matnlar va tugmalar (o‘zbekcha)
db.py         — ma’lumotlar bazasi modellari va yordamchi funksiyalar
```

Matnlarni tahrirlash uchun `texts.py`, shahar/guruh sozlamalari uchun
`config.py` ni o‘zgartiring.
