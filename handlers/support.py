"""
handlers/support.py — Support screen.
General support → @notnow1122  |  Developer → @iam_esh
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message

import database as db
from config import DEVELOPER_USERNAME, GENERAL_SUPPORT_USERNAME
from emojis import e, divider
from keyboards import support_keyboard, BTN_SUPPORT

logger = logging.getLogger(__name__)
router = Router()


# Exact match on button text
@router.message(F.text == BTN_SUPPORT)
async def support_handler(message: Message, bot: Bot):
    try:
        caption = (
            f"{e('support')} <b>Support</b>\n"
            f"{divider()}"
            f"{e('user')} <b>General Support:</b> @{GENERAL_SUPPORT_USERNAME}\n"
            f"{e('crown')} <b>Developer:</b> <code>{DEVELOPER_USERNAME}</code>\n"
            f"{divider()}"
            f"{e('tip')} Tap a button below to reach out."
        )
        file_id = await db.get_image("support")
        if file_id:
            await bot.send_photo(chat_id=message.chat.id, photo=file_id,
                                 caption=caption, parse_mode="HTML",
                                 reply_markup=support_keyboard())
        else:
            await bot.send_message(chat_id=message.chat.id, text=caption,
                                   parse_mode="HTML", reply_markup=support_keyboard())
    except Exception as ex:
        logger.error(f"support_handler uid={message.from_user.id}: {ex}", exc_info=True)
