"""
handlers/balance.py — Balance screen.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message

import database as db
from emojis import e, divider
from keyboards import BTN_BALANCE

logger = logging.getLogger(__name__)
router = Router()


async def send_balance_screen(bot: Bot, chat_id: int, user_id: int):
    try:
        user = await db.get_user(user_id)
        if not user:
            return
        points = round(user["points"], 2)
        uname  = f"@{user['username']}" if user.get("username") else "—"
        caption = (
            f"{e('crown')} <b>Your Balance</b>\n"
            f"{divider()}"
            f"{e('user')} <i>{user['full_name']}</i>  {e('id')} <code>{user['telegram_id']}</code>\n"
            f"{e('link')} {uname}\n"
            f"{divider()}"
            f"{e('points')} <b>{points}</b> points"
        )
        file_id = await db.get_image("balance")
        if file_id:
            await bot.send_photo(chat_id=chat_id, photo=file_id,
                                 caption=caption, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")
    except Exception as ex:
        logger.error(f"send_balance_screen uid={user_id}: {ex}", exc_info=True)


# Exact match on button text — prevents accidental swallowing of unrelated messages
@router.message(F.text == BTN_BALANCE)
async def balance_handler(message: Message, bot: Bot):
    try:
        await send_balance_screen(bot, message.chat.id, message.from_user.id)
    except Exception as ex:
        logger.error(f"balance_handler uid={message.from_user.id}: {ex}", exc_info=True)
