"""
handlers/refer.py — Referral system screen.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery

import database as db
from emojis import e, divider
from keyboards import refer_keyboard, refer_back_keyboard, BTN_REFER

logger = logging.getLogger(__name__)
router = Router()


async def send_refer_screen(bot: Bot, chat_id: int, user_id: int, bot_username: str):
    try:
        user = await db.get_user(user_id)
        if not user:
            return
        code        = user.get("referral_code", "")
        ref_count   = await db.get_referral_count(user_id)
        pts_per_ref = await db.get_setting("points_per_refer", "5")
        ref_link    = f"https://t.me/{bot_username}?start=ref_{code}" if code else "N/A"

        caption = (
            f"{e('refer')} <b>Refer & Earn</b>\n"
            f"{divider()}"
            f"{e('tip')} Earn <b>{pts_per_ref} pts</b> for every friend who joins.\n"
            f"{divider()}"
            f"{e('link')} <b>Your Link:</b>\n"
            f"<code>{ref_link}</code>\n"
            f"{divider()}"
            f"{e('refer_menu')} <b>Referrals:</b> <code>{ref_count}</code>"
        )
        file_id = await db.get_image("refer")
        if file_id:
            await bot.send_photo(chat_id=chat_id, photo=file_id,
                                 caption=caption, parse_mode="HTML",
                                 reply_markup=refer_keyboard())
        else:
            await bot.send_message(chat_id=chat_id, text=caption,
                                   parse_mode="HTML", reply_markup=refer_keyboard())
    except Exception as ex:
        logger.error(f"send_refer_screen uid={user_id}: {ex}", exc_info=True)


# Exact match on button text
@router.message(F.text == BTN_REFER)
async def refer_handler(message: Message, bot: Bot):
    try:
        me = await bot.get_me()
        await send_refer_screen(bot, message.chat.id, message.from_user.id, me.username)
    except Exception as ex:
        logger.error(f"refer_handler uid={message.from_user.id}: {ex}", exc_info=True)


@router.callback_query(F.data == "my_refer")
async def cb_my_refer(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        refs = await db.get_referrals(callback.from_user.id)
        lines = [f"{e('refer_menu')} <b>Your Referrals</b>\n{divider()}"]
        if refs:
            for i, r in enumerate(refs[:20], 1):
                name  = r.get("full_name", "Unknown")
                uname = f"@{r['username']}" if r.get("username") else "—"
                lines.append(f"<b>{i}.</b> <i>{name}</i> — <code>{uname}</code>")
        else:
            lines.append("<i>No referrals yet.</i>")
        await callback.message.answer("\n".join(lines), parse_mode="HTML",
                                      reply_markup=refer_back_keyboard())
    except Exception as ex:
        logger.error(f"cb_my_refer uid={callback.from_user.id}: {ex}", exc_info=True)


@router.callback_query(F.data == "top_lists")
async def cb_top_lists(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        top    = await db.get_top_referrers(10)
        medals = ["🥇", "🥈", "🥉"]
        lines  = [f"{e('crown')} <b>Top Referrers</b>\n{divider()}"]
        if top:
            for i, row in enumerate(top, 1):
                medal = medals[i - 1] if i <= 3 else f"{i}."
                lines.append(
                    f"{medal} <i>{row['full_name'] or 'Unknown'}</i>"
                    f" — <code>{row['ref_count']}</code> referrals"
                )
        else:
            lines.append("<i>No data yet.</i>")
        await callback.message.answer("\n".join(lines), parse_mode="HTML",
                                      reply_markup=refer_back_keyboard())
    except Exception as ex:
        logger.error(f"cb_top_lists uid={callback.from_user.id}: {ex}", exc_info=True)


@router.callback_query(F.data == "refer_back")
async def cb_refer_back(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        me = await bot.get_me()
        try:
            await callback.message.delete()
        except Exception:
            pass
        await send_refer_screen(bot, callback.message.chat.id,
                                 callback.from_user.id, me.username)
    except Exception as ex:
        logger.error(f"cb_refer_back uid={callback.from_user.id}: {ex}", exc_info=True)
