"""
handlers/stock.py — Live stock availability screen.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message

import database as db
from api.jap import jap
from emojis import e, divider
from keyboards import BTN_STOCK

logger = logging.getLogger(__name__)
router = Router()


async def _service_status(service_id: str) -> tuple[str, str]:
    if not service_id:
        return f"{e('warning')} <i>Not Configured</i>", "—"
    services = await jap.get_services()
    if services is None:
        return f"{e('loading')} <i>Checking…</i>", "—"
    for svc in services:
        if str(svc.get("service", "")) == str(service_id):
            max_q = svc.get("max", "∞")
            return f"{e('success')} <b>In Stock</b>", str(max_q)
    return f"{e('error')} <i>Not Found</i>", "—"


# Exact match on button text
@router.message(F.text == BTN_STOCK)
async def stock_handler(message: Message, bot: Bot):
    try:
        fol_sid = await db.get_setting("jap_followers_service_id", "")
        lik_sid = await db.get_setting("jap_likes_service_id", "")
        vie_sid = await db.get_setting("jap_views_service_id", "")
        com_sid = await db.get_setting("jap_comments_service_id", "")

        sent = await message.answer(
            f"{e('loading')} <b>Fetching live stock…</b>", parse_mode="HTML"
        )

        fol_status, fol_max = await _service_status(fol_sid)
        lik_status, lik_max = await _service_status(lik_sid)
        vie_status, vie_max = await _service_status(vie_sid)
        com_status, com_max = await _service_status(com_sid)

        caption = (
            f"{e('botstats')} <b>LIVE STOCK STATUS</b> {e('live')}\n"
            f"{divider()}"
            f"<blockquote>{e('tip')} Real-time availability from the panel.</blockquote>\n"
            f"{divider()}"
            f"{e('followers')} <b>Followers</b>\n"
            f"   Status: {fol_status}   Max: <code>{fol_max}</code>\n\n"
            f"{e('likes')} <b>Likes</b>\n"
            f"   Status: {lik_status}   Max: <code>{lik_max}</code>\n\n"
            f"{e('views')} <b>Views</b>\n"
            f"   Status: {vie_status}   Max: <code>{vie_max}</code>\n\n"
            f"{e('comments')} <b>Comments</b>\n"
            f"   Status: {com_status}   Max: <code>{com_max}</code>\n"
            f"{divider()}"
            f"{e('fire')} <i>Order fast before stock runs out!</i>"
        )
        file_id = await db.get_image("stock")
        try:
            await sent.delete()
        except Exception:
            pass
        if file_id:
            await bot.send_photo(chat_id=message.chat.id, photo=file_id,
                                 caption=caption, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=message.chat.id, text=caption, parse_mode="HTML")
    except Exception as ex:
        logger.error(f"stock_handler uid={message.from_user.id}: {ex}", exc_info=True)
