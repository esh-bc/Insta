"""
handlers/giftcode.py — Gift code screen and redemption flow.
"""
import logging
from datetime import datetime, timezone

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

import database as db
from config import GIFT_CODE_COOLDOWN
from emojis import e, divider
from keyboards import giftcode_keyboard, back_keyboard, main_menu_keyboard, BTN_GIFT

logger = logging.getLogger(__name__)
router = Router()


class GiftStates(StatesGroup):
    entering_code = State()


async def send_giftcode_screen(bot: Bot, chat_id: int):
    try:
        caption = (
            f"{e('gift')} <b>Gift Codes</b>\n"
            f"{divider()}"
            f"{e('tip')} Enter a gift code to claim free points!\n"
            f"{e('sparkle')} Codes are released regularly — stay tuned."
        )
        file_id = await db.get_image("giftcode")
        if file_id:
            await bot.send_photo(chat_id=chat_id, photo=file_id,
                                 caption=caption, parse_mode="HTML",
                                 reply_markup=giftcode_keyboard())
        else:
            await bot.send_message(chat_id=chat_id, text=caption,
                                   parse_mode="HTML", reply_markup=giftcode_keyboard())
    except Exception as ex:
        logger.error(f"send_giftcode_screen chat={chat_id}: {ex}", exc_info=True)


# Exact match on button text
@router.message(F.text == BTN_GIFT)
async def giftcode_handler(message: Message, bot: Bot):
    try:
        await send_giftcode_screen(bot, message.chat.id)
    except Exception as ex:
        logger.error(f"giftcode_handler uid={message.from_user.id}: {ex}", exc_info=True)


@router.message(Command("redeem"))
async def cmd_redeem(message: Message, state: FSMContext):
    try:
        await state.set_state(GiftStates.entering_code)
        await message.answer(
            f"{e('gift')} <b>Enter your gift code:</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard("go_main_menu"),
        )
    except Exception as ex:
        logger.error(f"cmd_redeem uid={message.from_user.id}: {ex}", exc_info=True)


@router.callback_query(F.data == "open_redeem")
async def cb_open_redeem(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(GiftStates.entering_code)
        await callback.message.answer(
            f"{e('gift')} <b>Enter your gift code:</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard("go_main_menu"),
        )
    except Exception as ex:
        logger.error(f"cb_open_redeem uid={callback.from_user.id}: {ex}", exc_info=True)


@router.message(GiftStates.entering_code, F.text)
async def handle_redeem_code(message: Message, state: FSMContext, bot: Bot):
    try:
        user_id  = message.from_user.id
        code_str = (message.text or "").strip().upper()

        if not code_str:
            await message.answer(f"{e('error')} Please enter a valid code.", parse_mode="HTML")
            return

        # Cooldown check
        last = await db.get_last_redeem_time(user_id)
        if last:
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            if elapsed < GIFT_CODE_COOLDOWN:
                remaining = int(GIFT_CODE_COOLDOWN - elapsed)
                await state.clear()
                await message.answer(
                    f"{e('warning')} <b>Cooldown active.</b>\n"
                    f"Wait <b>{remaining}s</b> before redeeming another code.",
                    parse_mode="HTML",
                )
                return

        code = await db.get_gift_code(code_str)
        if not code:
            await state.clear()
            await message.answer(
                f"{e('error')} <b>Invalid code.</b>",
                parse_mode="HTML",
            )
            return

        # Expiry
        if code.get("expires_at") and code["expires_at"] < datetime.now(timezone.utc):
            await state.clear()
            await message.answer(
                f"{e('error')} <b>This code has expired.</b>",
                parse_mode="HTML",
            )
            return

        # Max uses
        if code["used_count"] >= code["max_uses"]:
            await state.clear()
            await message.answer(
                f"{e('error')} <b>This code has reached its use limit.</b>",
                parse_mode="HTML",
            )
            return

        # Already redeemed
        if await db.has_redeemed(code_str, user_id):
            await state.clear()
            await message.answer(
                f"{e('error')} <b>You already redeemed this code.</b>",
                parse_mode="HTML",
            )
            return

        # ── Credit points ──────────────────────────────────────────────
        pts = float(code["points"])
        await db.add_points(user_id, pts)
        await db.increment_code_use(code_str)
        await db.add_redemption(code_str, user_id)
        await db.set_last_redeem_time(user_id)
        await state.clear()

        user    = await db.get_user(user_id)
        new_bal = round(user["points"], 2) if user else "?"
        await message.answer(
            f"{e('success')} <b>Code redeemed!</b>\n"
            f"{divider()}"
            f"{e('gift')} <code>{code_str}</code>  →  <b>+{pts} pts</b>\n"
            f"{e('balance')} New balance: <b>{new_bal} pts</b>",
            parse_mode="HTML",
        )
    except Exception as ex:
        logger.error(f"handle_redeem_code uid={message.from_user.id}: {ex}", exc_info=True)
        await state.clear()
        await message.answer(
            f"{e('error')} Something went wrong. Please try again.",
            parse_mode="HTML",
        )
