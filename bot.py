import os
import re
import asyncio
from typing import Optional
from urllib.parse import quote
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.markdown import hbold
from aiogram.types import FSInputFile

from config import load_config
from db import DB

cfg = load_config()
db = DB("bot.db")
dp = Dispatcher()

# ✅ Admin ID
ADMIN_ID = 5037587016

TZ = ZoneInfo("Asia/Tashkent")


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def current_target() -> int:
    return db.get_target(cfg.INVITE_TARGET)


def today_start_ts() -> int:
    now = datetime.now(TZ)
    start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=TZ)
    return int(start.timestamp())


# ---------- UX helpers ----------
def progress_bar(count: int, target: int, width: int = 10) -> str:
    if target <= 0:
        return ""
    filled = int(round((count / target) * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


# ---------- Reply Keyboards (PANELS) ----------
def kb_user_panel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📈 Progressim"), KeyboardButton(text="🔗 Referal havolam")],
            [KeyboardButton(text="🏆 TOP-10"), KeyboardButton(text="📅 Bugungi natija")],
            [KeyboardButton(text="✅ Obunani tekshirish"), KeyboardButton(text="ℹ️ Yordam")],
            [KeyboardButton(text="🧾 Menyu")],
        ],
        resize_keyboard=True
    )


def kb_admin_panel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Hisobot"), KeyboardButton(text="🏆 TOP-10")],
            [KeyboardButton(text="🔥 4/5 ro‘yxati"), KeyboardButton(text="🧹 Hammasini 0")],
            [KeyboardButton(text="♻️ User reset"), KeyboardButton(text="🎯 Targetni o‘zgartirish")],
            [KeyboardButton(text="🧾 Menyu")],
        ],
        resize_keyboard=True
    )


# ---------- Inline Keyboards ----------
def kb_subscribe(public_channel: str) -> InlineKeyboardMarkup:
    username = public_channel.strip().lstrip("@").strip()
    username = re.sub(r"[^a-zA-Z0-9_]", "", username)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Kanalga o‘tish", url=f"https://t.me/{username}")],
        [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]
    ])


def kb_share(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    share_link = quote(link, safe="")
    share_text = quote("Men ham qo‘shildim! Siz ham kirib ko‘ring:", safe="")
    share_url = f"https://t.me/share/url?url={share_link}&text={share_text}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Havolani ulashish", url=share_url)],
        [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")]
    ])


# ---------- Helpers ----------
async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id=cfg.PUBLIC_CHANNEL, user_id=user_id)
        return m.status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        }
    except (TelegramBadRequest, TelegramForbiddenError):
        return False


def parse_referrer(start_text: str) -> Optional[int]:
    m = re.search(r"ref_(\d+)", start_text)
    return int(m.group(1)) if m else None


async def send_main_post(bot: Bot, user_id: int):
    """
    ✅ Obuna tasdiqlangandan keyin bitta post:
    - assets/kuch.jpg
    - caption: siz bergan matn
    """
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user_id}"

    target = current_target()
    count = db.referrals_count(user_id)
    bar = progress_bar(count, target)

    caption = (
        f"{hbold('Kuchlilar')} 💪\n\n"
        f"Quyidagi havola orqali botga kiring, yopiq kanalga qo'shiling  va darslarni ko'rish imkonini qo'lga kiriting:\n"
        f"{link}\n\n"
        f"📈 Progress: {bar} {count}/{target}\n\n"
        f"Kuchlilar — odatlar, maqsadlar va intizom asosida kuchli insonlarni yetishtiradigan loyiha.\n"
        f"Bu yerda: 🔹 odatlar 🔹 maqsadlar 🔹 intizom 🔹 rivojlanish 🔹 kitob 🔹 sport 🔹 real tajribalar.\n\n"
        f"2026 yilda maxsus darslarni alohida yopiq kanalga joyladik.\n"
        f"U yerga kirish uchun {target} ta yaqin insoningizni taklif qiling."
    )

    photo_path = os.path.join("assets", "kuch.jpg")
    await bot.send_photo(
        chat_id=user_id,
        photo=FSInputFile(photo_path),
        caption=caption,
        reply_markup=kb_share(me.username, user_id),
    )


async def maybe_notify_and_reward(bot: Bot, referrer_id: int):
    """
    ✅ 4/5 -> deyarlibo'ldi (1 marta)
    ✅ 5/5 -> G'ALABA + invite (1 marta)
    """
    target = current_target()
    cnt = db.referrals_count(referrer_id)

    # 4/5
    if cnt == target - 1 and not db.flag_set(referrer_id, "near_sent"):
        if db.set_flag(referrer_id, "near_sent"):
            await bot.send_message(
                referrer_id,
                "🔥 DEYARLI BO‘LDI!\n\n"
                f"Siz {cnt}/{target} ga yetdingiz.\n"
                "Yana 1 ta odam qoldi 💪"
            )

    # 5/5
    if cnt >= target and not db.flag_set(referrer_id, "win_sent"):
        if db.set_flag(referrer_id, "win_sent"):
            try:
                invite = await bot.create_chat_invite_link(
                    chat_id=cfg.PRIVATE_CHANNEL_ID,
                    member_limit=1,
                    name=f"reward_{referrer_id}"
                )
                await bot.send_message(
                    referrer_id,
                    "🏁 G‘ALABA! 🎉\n\n"
                    f"Siz {target} ta odamni taklif qildingiz.\n"
                    f"🔐 Yopiq kanalga 1 martalik kirish havolasi:\n{invite.invite_link}"
                )
            except TelegramForbiddenError:
                await bot.send_message(
                    referrer_id,
                    "❌ Invite link bera olmadim.\n"
                    "Bot yopiq kanalga ADMIN qilinganmi? Invite link yaratish huquqi bormi?"
                )
            except TelegramBadRequest as e:
                await bot.send_message(referrer_id, f"❌ Invite link xatosi: {e.message}")


# =========================
#   MENYU / PANELLAR
# =========================
@dp.message(F.text.in_({"🧾 Menyu", "/menu", "menu"}))
async def menu_cmd(message: Message):
    uid = message.from_user.id
    if db.is_banned(uid):
        return

    if is_admin(uid):
        await message.answer("🛠 Admin menyu:", reply_markup=kb_admin_panel())
    else:
        await message.answer("✅ Menyu:", reply_markup=kb_user_panel())


# =========================
#   USER BUTTONS
# =========================
@dp.message(F.text == "📈 Progressim")
async def user_progress(message: Message):
    uid = message.from_user.id
    target = current_target()
    cnt = db.referrals_count(uid)
    bar = progress_bar(cnt, target)
    rank = db.user_rank(uid)
    await message.answer(f"📈 Progress: {bar} {cnt}/{target}\n🏅 Reyting: #{rank}")


@dp.message(F.text == "🔗 Referal havolam")
async def user_ref_link(message: Message, bot: Bot):
    me = await bot.get_me()
    uid = message.from_user.id
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    await message.answer(f"🔗 Sizning referal havolangiz:\n{link}")


@dp.message(F.text == "✅ Obunani tekshirish")
async def user_check_sub(message: Message, bot: Bot):
    uid = message.from_user.id
    ok = await is_subscribed(bot, uid)
    if ok:
        db.set_joined_ok(uid, True)
        await message.answer("✅ Obuna tasdiqlandi!")
        await send_main_post(bot, uid)
    else:
        await message.answer(
            "❌ Hali obuna bo‘lmagansiz. Avval kanalga obuna bo‘ling 👇",
            reply_markup=kb_subscribe(cfg.PUBLIC_CHANNEL)
        )


@dp.message(F.text == "🏆 TOP-10")
async def user_top10(message: Message):
    top = db.top_referrers(10)
    if not top:
        await message.answer("Hali TOP-10 yo‘q.")
        return

    target = current_target()
    lines = [f"🏆 {hbold('TOP-10 Reyting')}\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, cnt) in enumerate(top, start=1):
        medal = medals[i-1] if i <= 3 else f"{i})"
        bar = progress_bar(cnt, target)
        lines.append(f"{medal} {uid} — {bar} {cnt}/{target}")

    await message.answer("\n".join(lines))


@dp.message(F.text == "📅 Bugungi natija")
async def user_today(message: Message):
    uid = message.from_user.id
    since = today_start_ts()
    today_cnt = db.referrals_count_since(uid, since)
    await message.answer(f"📅 Bugungi natijangiz: {today_cnt} ta referral ✅")


@dp.message(F.text == "ℹ️ Yordam")
async def user_help(message: Message):
    target = current_target()
    await message.answer(
        "ℹ️ Yordam:\n"
        "1) Kanalga obuna bo‘ling\n"
        "2) '✅ Obunani tekshirish' ni bosing\n"
        "3) '🔗 Referal havolam' ni do‘stlaringizga ulashing\n\n"
        f"🎁 {target} ta odam taklif qilsangiz — yopiq kanal linki beriladi."
    )


# =========================
#   ADMIN BUTTONS
# =========================
@dp.message(F.text == "📊 Hisobot")
async def admin_stats_btn(message: Message):
    if not is_admin(message.from_user.id):
        return

    users = db.users_count()
    refs = db.referrals_total()
    target = current_target()

    # bugungi top-10
    since = today_start_ts()
    top_today = db.top_referrers_since(since, 10)

    txt = (
        f"📊 {hbold('Admin Hisobot')}\n\n"
        f"👥 Userlar: {users}\n"
        f"🔗 Jami referral: {refs}\n"
        f"🎯 Target: {target}\n\n"
        f"📅 Bugungi TOP-10 (son): {', '.join(str(c) for _, c in top_today) if top_today else 'yo‘q'}"
    )
    await message.answer(txt)


@dp.message(F.text == "🔥 4/5 ro‘yxati")
async def admin_near_btn(message: Message):
    if not is_admin(message.from_user.id):
        return
    target = current_target()
    near = db.users_near_goal(target - 1, limit=50)
    if not near:
        await message.answer("Hozircha 4/5 ga yetgan userlar yo‘q.")
        return

    lines = [f"🔥 {hbold('4/5 dagilar ro‘yxati')}\n"]
    for uid, cnt in near:
        lines.append(f"• {uid} — {cnt}/{target}")
    await message.answer("\n".join(lines))


@dp.message(F.text == "🧹 Hammasini 0")
async def admin_wipe_btn(message: Message):
    if not is_admin(message.from_user.id):
        return
    db.wipe_all_referrals()
    await message.answer("✅ Hammasi 0 qilindi: referral + flaglar tozalandi.")


@dp.message(F.text == "♻️ User reset")
async def admin_reset_hint(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("User reset: /reset_user 123456789")


@dp.message(F.text == "🎯 Targetni o‘zgartirish")
async def admin_target_hint(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Target o‘zgartirish: /set_target 5")


# =========================
#   ADMIN COMMANDS
# =========================
@dp.message(F.text.startswith("/set_target"))
async def admin_set_target(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("To‘g‘ri format: /set_target 5")
        return
    n = int(parts[1])
    if n < 1 or n > 1000:
        await message.answer("Target 1..1000 oralig‘ida bo‘lsin.")
        return
    db.set_target(n)
    await message.answer(f"✅ Target yangilandi: {n}")


@dp.message(F.text.startswith("/reset_user"))
async def admin_reset_user(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Format: /reset_user 123456789")
        return
    uid = int(parts[1])
    db.reset_user_progress(uid)
    await message.answer(f"✅ Reset qilindi: {uid}")


# =========================
#   START / CHECK_SUB
# =========================
@dp.message(F.text.startswith("/start"))
async def start(message: Message, bot: Bot):
    text = message.text or "/start"
    user_id = message.from_user.id

    referrer_id = parse_referrer(text)
    if referrer_id == user_id:
        referrer_id = None

    db.ensure_user(user_id, referrer_id=referrer_id)

    if db.is_banned(user_id):
        await message.answer("⛔ Siz botdan foydalanishdan cheklangansiz.")
        return

    # menyu
    if is_admin(user_id):
        await message.answer("🛠 Admin menyu:", reply_markup=kb_admin_panel())
    else:
        await message.answer("✅ Menyu:", reply_markup=kb_user_panel())

    # obuna tekshir
    if not await is_subscribed(bot, user_id):
        await message.answer("Davom etish uchun kanalga obuna bo‘ling 👇", reply_markup=kb_subscribe(cfg.PUBLIC_CHANNEL))
        return

    db.set_joined_ok(user_id, True)
    await send_main_post(bot, user_id)


@dp.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id

    if db.is_banned(user_id):
        await call.answer("⛔ Siz cheklangansiz.", show_alert=True)
        return

    ok = await is_subscribed(bot, user_id)
    if not ok:
        await call.answer("Hali obuna bo‘lmagansiz.", show_alert=True)
        return

    db.set_joined_ok(user_id, True)

    # ✅ referral faqat shu yerda sanaladi
    u = db.get_user(user_id)
    if u:
        _, ref_id, joined_ok, banned = u
        if (not banned) and joined_ok and ref_id and ref_id != user_id:
            added = db.add_referral_if_unique(ref_id, user_id)
            if added:
                try:
                    target = current_target()
                    cnt = db.referrals_count(ref_id)
                    bar = progress_bar(cnt, target)
                    await bot.send_message(ref_id, f"✅ Yangi taklif: +1\n📈 {bar} {cnt}/{target}")
                    await maybe_notify_and_reward(bot, ref_id)
                except TelegramForbiddenError:
                    pass

    # UX: eski xabarni o'chirish
    try:
        if call.message:
            await call.message.delete()
    except:
        pass

    await call.answer("✅ Obuna tasdiqlandi!", show_alert=False)
    await send_main_post(bot, user_id)


# ---------- Main ----------
async def main():
    bot = Bot(
        token=cfg.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())