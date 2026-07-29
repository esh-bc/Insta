"""
handlers/start.py — /start command, force join, promo, maintenance gate, and main menu.
Added: persistent "Main Menu" button handler, /help command.
"""

import json
import logging
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, StateFilter, Command
from aiogram.types import Message, CallbackQuery, MessageEntity, User as TgUser
from aiogram.fsm.context import FSMContext

import database as db
from config import BOT_NAME, MASTER_ADMIN_ID
from emojis import e, divider
from keyboards import (
    continue_button, force_join_keyboard, try_again_keyboard,
    main_menu_keyboard, error_keyboard, BTN_MAIN_MENU,
)

logger = logging.getLogger(__name__)
router = Router()


# ─── helpers ─────────────────────────────────────────────────────────────────

def _deserialize_entities(entities_json: str) -> list[MessageEntity]:
    """
    Deserialise a JSON-stored entity list back to MessageEntity objects.
    Correctly handles custom_emoji entities (premium animated emojis) so
    that the custom_emoji_id field is preserved through DB round-trips.
    """
    if not entities_json:
        return []
    try:
        raw_list = json.loads(entities_json)
        entities = []
        for d in raw_list:
            # Ensure custom_emoji_id surfaces correctly for MessageEntity validation
            if d.get("type") == "custom_emoji" and d.get("custom_emoji_id"):
                # model_validate handles this but let's be explicit
                pass
            try:
                entities.append(MessageEntity.model_validate(d))
            except Exception as inner:
                logger.warning(f"_deserialize_entities skip entity {d}: {inner}")
        return entities
    except Exception as ex:
        logger.warning(f"_deserialize_entities: {ex}")
        return []


def _u16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _apply_mention_placeholder(
    text: str, entities: list[MessageEntity],
    user_id: int, full_name: str,
) -> tuple[str, list[MessageEntity]]:
    PLACEHOLDER = "[full]"
    pos = text.find(PLACEHOLDER)
    if pos == -1:
        return text, entities

    new_text = text[:pos] + full_name + text[pos + len(PLACEHOLDER):]

    pos_u16         = _u16(text[:pos])
    placeholder_u16 = _u16(PLACEHOLDER)
    fullname_u16    = _u16(full_name)
    delta           = fullname_u16 - placeholder_u16
    end_u16         = pos_u16 + placeholder_u16

    adjusted: list[MessageEntity] = []
    for ent in entities:
        off      = ent.offset
        length   = ent.length
        ent_end  = off + length

        if ent_end <= pos_u16:
            pass
        elif off >= end_u16:
            off += delta
        elif off <= pos_u16 and ent_end >= end_u16:
            length += delta
        else:
            continue

        d = ent.model_dump(mode="json")
        d["offset"] = off
        d["length"] = length
        adjusted.append(MessageEntity.model_validate(d))

    adjusted.append(MessageEntity(
        type="text_mention",
        offset=pos_u16,
        length=fullname_u16,
        user=TgUser(id=user_id, is_bot=False, first_name=full_name),
    ))
    adjusted.sort(key=lambda ent: ent.offset)
    return new_text, adjusted


async def _show_promo(
    bot: Bot, chat_id: int, user_id: int,
    full_name: str, is_verified: bool,
) -> bool:
    """Send the promo message. Returns True if shown."""
    promo_text     = await db.get_setting("promo_text", "")
    promo_mode     = await db.get_setting("promo_mode", "always")
    promo_entities = await db.get_setting("promo_entities", "")

    if not promo_text:
        return False

    # "once" mode — only show first time
    if promo_mode == "once" and is_verified:
        return False

    text     = promo_text
    entities = _deserialize_entities(promo_entities)
    text, entities = _apply_mention_placeholder(text, entities, user_id, full_name)

    file_id = await db.get_image("promo")
    try:
        if file_id:
            await bot.send_photo(
                chat_id=chat_id, photo=file_id,
                caption=text, caption_entities=entities or None,
                reply_markup=continue_button(),
            )
        else:
            await bot.send_message(
                chat_id=chat_id, text=text,
                entities=entities or None,
                reply_markup=continue_button(),
            )
        return True
    except Exception as ex:
        logger.error(f"_show_promo uid={user_id}: {ex}", exc_info=True)
        return False


async def send_main_menu(
    bot: Bot, chat_id: int, full_name: str,
    bot_name: str, user_id: int = 0,
):
    """Send the main menu greeting."""
    menu_text     = await db.get_setting("menu_text", "")
    menu_entities = await db.get_setting("menu_entities", "")

    if menu_text:
        text     = menu_text
        entities = _deserialize_entities(menu_entities)
        if user_id:
            text, entities = _apply_mention_placeholder(text, entities, user_id, full_name)
        file_id = await db.get_image("main")
        try:
            if file_id:
                await bot.send_photo(
                    chat_id=chat_id, photo=file_id,
                    caption=text, caption_entities=entities or None,
                    reply_markup=main_menu_keyboard(),
                )
            else:
                await bot.send_message(
                    chat_id=chat_id, text=text,
                    entities=entities or None,
                    reply_markup=main_menu_keyboard(),
                )
            return
        except Exception as ex:
            logger.error(f"send_main_menu menu_text: {ex}", exc_info=True)

    # Default menu
    caption = (
        f"{e('welcome')} <b>Welcome, {full_name}!</b>\n"
        f"{divider()}"
        f"{e('instagram')} <b>{bot_name}</b>\n"
        f"{e('tip')} Use the menu below to get started."
    )
    file_id = await db.get_image("main")
    try:
        if file_id:
            await bot.send_photo(chat_id=chat_id, photo=file_id,
                                 caption=caption, parse_mode="HTML",
                                 reply_markup=main_menu_keyboard())
        else:
            await bot.send_message(chat_id=chat_id, text=caption,
                                   parse_mode="HTML", reply_markup=main_menu_keyboard())
    except Exception as ex:
        logger.error(f"send_main_menu uid={user_id}: {ex}", exc_info=True)


async def _show_force_join(bot: Bot, chat_id: int, channels: list):
    caption = (
        f"{e('channel')} <b>Join our channels</b>\n"
        f"{divider()}"
        f"{e('tip')} Join all channels below to unlock the bot.\n"
        f"Then tap <b>I Joined All</b>."
    )
    file_id = await db.get_image("welcome")
    try:
        if file_id:
            await bot.send_photo(chat_id=chat_id, photo=file_id,
                                 caption=caption, parse_mode="HTML",
                                 reply_markup=force_join_keyboard(channels))
        else:
            await bot.send_message(chat_id=chat_id, text=caption,
                                   parse_mode="HTML",
                                   reply_markup=force_join_keyboard(channels))
    except Exception as ex:
        logger.error(f"_show_force_join: {ex}", exc_info=True)


async def _credit_referrer(bot: Bot, new_user, referrer_id: int) -> None:
    try:
        pts = float(await db.get_setting("points_per_refer", "5"))
        ok  = await db.add_referral(referrer_id, new_user.id)
        if ok:
            await db.add_points(referrer_id, pts)
            try:
                await bot.send_message(
                    referrer_id,
                    f"{e('bonus')} <b>Referral bonus!</b>\n"
                    f"{e('user')} {new_user.full_name} joined.\n"
                    f"{e('points')} <b>+{pts} pts</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception as ex:
        logger.error(f"_credit_referrer ref={referrer_id}: {ex}", exc_info=True)


# ─── /start ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    try:
        await state.clear()
        user     = message.from_user
        args     = message.text.split(maxsplit=1)
        ref_code = None
        if len(args) > 1 and args[1].startswith("ref_"):
            ref_code = args[1].replace("ref_", "")

        # Maintenance gate (skip for master admin)
        if user.id != MASTER_ADMIN_ID:
            if await db.is_maintenance():
                await message.answer(
                    f"{e('maintenance')} <b>Bot is under maintenance.</b>\n"
                    f"{divider()}"
                    f"{e('tip')} We'll be back soon. Please wait.",
                    parse_mode="HTML",
                )
                return

        # Resolve referrer — guard against self-referral
        referrer_id = None
        if ref_code:
            referrer = await db.get_user_by_referral_code(ref_code)
            if referrer and referrer["telegram_id"] != user.id:
                referrer_id = referrer["telegram_id"]

        # Create or update user
        db_user = await db.get_user(user.id)
        if not db_user:
            db_user = await db.create_user(
                user.id,
                user.username or "",
                user.full_name or "Unknown",
                referred_by=referrer_id,
            )
        else:
            await db.update_user_info(user.id, user.username or "", user.full_name or "Unknown")

        # Captcha check
        captcha_on = await db.get_setting("captcha_enabled", "0")
        if captcha_on == "1" and not db_user["is_verified"] and user.id != MASTER_ADMIN_ID:
            import random
            a, b = random.randint(1, 9), random.randint(1, 9)
            await state.set_state("captcha_check")
            await state.update_data(captcha_answer=a + b)
            await message.answer(
                f"{e('captcha')} <b>Security check</b>\n"
                f"{divider()}"
                f"What is <b>{a} + {b}</b>?",
                parse_mode="HTML",
            )
            return

        # Check force-join channels
        channels = await db.get_all_channels()
        if channels and not db_user["is_verified"] and user.id != MASTER_ADMIN_ID:
            await _show_force_join(bot, message.chat.id, channels)
            return

        # No channels configured — auto-verify
        if not channels and not db_user["is_verified"]:
            await db.set_user_verified(user.id, 1)
            db_user = await db.get_user(user.id)

        if not db_user["is_verified"] and user.id != MASTER_ADMIN_ID:
            await _show_force_join(bot, message.chat.id, channels)
            return

        # Show promo or main menu
        shown = await _show_promo(bot, message.chat.id, user.id,
                                  user.full_name, db_user["is_verified"])
        if not shown:
            await send_main_menu(bot, message.chat.id, user.full_name, BOT_NAME, user_id=user.id)

    except Exception as ex:
        logger.error(f"cmd_start uid={message.from_user.id}: {ex}", exc_info=True)


# ─── /help ───────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    try:
        text = (
            f"{e('tip')} <b>Bot Help</b>\n"
            f"{divider()}"
            f"{e('balance')} <b>Balance</b> — View your current points balance.\n"
            f"{e('refer')} <b>Refer</b> — Get your referral link and earn points for each friend who joins.\n"
            f"{e('botstats')} <b>Stock</b> — Check real-time availability of followers, likes, views, and comments.\n"
            f"{e('support')} <b>Support</b> — Contact our support team.\n"
            f"{e('proofs')} <b>Proofs</b> — View our proofs channel with completed order screenshots.\n"
            f"{e('gift')} <b>Gift Code</b> — Redeem a gift code for free points.\n"
            f"{e('withdraw')} <b>Withdraw</b> — Spend your points to order Instagram followers, likes, views, or comments.\n"
            f"{e('menu')} <b>Main Menu</b> — Reset to the main menu from anywhere in the bot.\n"
            f"{divider()}"
            f"<b>Commands:</b>\n"
            f"/start — Open the bot\n"
            f"/help — Show this help message\n"
            f"/redeem — Redeem a gift code\n"
            f"{divider()}"
            f"{e('tip')} Earn points by referring friends, then spend them on Instagram growth!"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard())
    except Exception as ex:
        logger.error(f"cmd_help uid={message.from_user.id}: {ex}", exc_info=True)


# ─── Persistent "Main Menu" button — resets FSM and shows main menu ──────────

@router.message(F.text == BTN_MAIN_MENU)
async def handle_main_menu_button(message: Message, bot: Bot, state: FSMContext):
    """Always-available Main Menu button — clears any active FSM state and returns user to menu."""
    try:
        await state.clear()
        user = message.from_user
        await send_main_menu(bot, message.chat.id, user.full_name, BOT_NAME, user_id=user.id)
    except Exception as ex:
        logger.error(f"handle_main_menu_button uid={message.from_user.id}: {ex}", exc_info=True)


# ─── Continue from promo ──────────────────────────────────────────────────────

@router.callback_query(F.data == "continue_promo")
async def cb_continue_promo(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        user    = callback.from_user
        db_user = await db.get_user(user.id)
        if not db_user:
            return

        channels = await db.get_all_channels()
        if channels and not db_user["is_verified"] and user.id != MASTER_ADMIN_ID:
            await _show_force_join(bot, callback.message.chat.id, channels)
            return

        if not db_user["is_verified"] and user.id != MASTER_ADMIN_ID:
            if channels:
                await _show_force_join(bot, callback.message.chat.id, channels)
            else:
                await db.set_user_verified(user.id, 1)
                await send_main_menu(bot, callback.message.chat.id,
                                     user.full_name, BOT_NAME, user_id=user.id)
            return

        await send_main_menu(bot, callback.message.chat.id,
                             user.full_name, BOT_NAME, user_id=user.id)
    except Exception as ex:
        logger.error(f"cb_continue_promo uid={callback.from_user.id}: {ex}", exc_info=True)


# ─── Check join callback ──────────────────────────────────────────────────────

@router.callback_query(F.data == "check_join")
async def cb_check_join(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        user     = callback.from_user
        channels = await db.get_all_channels()

        if not channels:
            await db.set_user_verified(user.id, 1)
            db_user = await db.get_user(user.id)
            if db_user and db_user.get("referred_by"):
                await _credit_referrer(bot, user, db_user["referred_by"])
            await send_main_menu(bot, callback.message.chat.id,
                                 user.full_name, BOT_NAME, user_id=user.id)
            return

        not_joined = []
        for ch in channels:
            cid = ch.get("channel_id")
            if not cid:
                continue
            try:
                member = await bot.get_chat_member(chat_id=int(cid), user_id=user.id)
                if member.status in ("left", "kicked", "banned", "restricted"):
                    not_joined.append(ch)
            except Exception as ex:
                logger.warning(f"check_join channel {cid}: {ex}")
                not_joined.append(ch)

        if not_joined:
            caption = (
                f"{e('error')} <b>You haven't joined all channels!</b>\n"
                f"{divider()}"
                f"{e('tip')} Please join <b>all</b> channels first."
            )
            try:
                await callback.message.edit_caption(
                    caption, parse_mode="HTML",
                    reply_markup=force_join_keyboard(channels),
                )
            except Exception:
                await callback.message.answer(
                    caption, parse_mode="HTML",
                    reply_markup=try_again_keyboard(),
                )
            return

        await db.set_user_verified(user.id, 1)
        db_user = await db.get_user(user.id)
        if db_user and db_user.get("referred_by"):
            await _credit_referrer(bot, user, db_user["referred_by"])
        await send_main_menu(bot, callback.message.chat.id,
                             user.full_name, BOT_NAME, user_id=user.id)

    except Exception as ex:
        logger.error(f"cb_check_join uid={callback.from_user.id}: {ex}", exc_info=True)


# ─── Close / main menu ────────────────────────────────────────────────────────

@router.callback_query(F.data == "close")
async def cb_close(callback: CallbackQuery):
    try:
        await callback.answer()
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "go_main_menu")
async def cb_go_main_menu(callback: CallbackQuery, bot: Bot, state: FSMContext):
    try:
        await callback.answer()
        await state.clear()           # always wipe any dangling FSM state
        user = callback.from_user
        await send_main_menu(bot, callback.message.chat.id,
                             user.full_name, BOT_NAME, user_id=user.id)
    except Exception as ex:
        logger.error(f"cb_go_main_menu uid={callback.from_user.id}: {ex}", exc_info=True)


# ─── Captcha ──────────────────────────────────────────────────────────────────

@router.message(F.text, StateFilter("captcha_check"))
async def handle_captcha_check(message: Message, bot: Bot, state: FSMContext):
    try:
        data     = await state.get_data()
        expected = data.get("captcha_answer")
        try:
            answer = int(message.text.strip())
        except ValueError:
            await message.answer(f"{e('error')} Enter a number.", parse_mode="HTML")
            return

        if answer == expected:
            await state.clear()
            user    = message.from_user
            db_user = await db.get_user(user.id)
            is_ver  = db_user["is_verified"] if db_user else False
            shown   = await _show_promo(bot, message.chat.id, user.id, user.full_name, is_ver)
            if not shown:
                await send_main_menu(bot, message.chat.id, user.full_name, BOT_NAME, user_id=user.id)
        else:
            await message.answer(
                f"{e('error')} Wrong answer. Try again.", parse_mode="HTML",
            )
    except Exception as ex:
        logger.error(f"handle_captcha_check uid={message.from_user.id}: {ex}", exc_info=True)
