"""
handlers/proofs.py — Proofs channel screen.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message

import database as db
from emojis import e, divider
from keyboards import proofs_keyboard, BTN_PROOFS

logger = logging.getLogger(__name__)
router = Router()


# Exact match on button text
@router.message(F.text == BTN_PROOFS)
async def proofs_handler(message: Message, bot: Bot):
    try:
        channel_link = await db.get_setting("proof_channel_link", "")
        caption = (
            f"{e('proofs')} <b>Order Proofs</b>\n"
            f"{divider()}"
            f"{e('verified')} Real proof of every completed order.\n"
            f"{e('tip')} Click below to see our proofs channel."
        )
        file_id = await db.get_image("proofs")
        kb      = proofs_keyboard(channel_link) if channel_link else None
        if file_id:
            await bot.send_photo(chat_id=message.chat.id, photo=file_id,
                                 caption=caption, parse_mode="HTML",
                                 reply_markup=kb)
        else:
            await bot.send_message(chat_id=message.chat.id, text=caption,
                                   parse_mode="HTML", reply_markup=kb)
    except Exception as ex:
        logger.error(f"proofs_handler uid={message.from_user.id}: {ex}", exc_info=True)
