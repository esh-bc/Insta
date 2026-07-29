"""
handlers/withdraw.py — Complete order flow with Instagram preview, amount input, and proof.
Fixed:
  • No more bot freeze on Instagram link — every API call has a strict asyncio.wait_for timeout
  • Reel/Likes/Comments → downloads thumbnail, shows account name, caption, like count
  • Followers → shows profile pic, bio, followers, following count
  • Service scope: "all" = profile link, "single" = post/reel link
  • Smooth FSM: choose service → enter link → preview → enter amount → confirm → proof
  • Rate limiting on link input (LINK_RATE_WINDOW / LINK_RATE_MAX from config)
  • Duplicate order guard (DUPLICATE_ORDER_WINDOW from config)
  • Auto-refund on manual "Check Status" if order is Cancelled/Failed
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, URLInputFile, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from api.jap import jap
from api.instagram import (
    fetch_profile_info, fetch_post_info, is_post_url,
    clean_username, _fmt_count, extract_shortcode,
)
from config import MASTER_ADMIN_ID, LINK_RATE_WINDOW, LINK_RATE_MAX, DUPLICATE_ORDER_WINDOW
from emojis import e, divider
from keyboards import (
    withdraw_service_keyboard, cancel_withdraw_keyboard,
    preview_continue_keyboard, preview_private_keyboard,
    skip_proof_keyboard, check_order_keyboard, main_menu_keyboard,
    error_keyboard, BTN_WITHDRAW,
)

logger = logging.getLogger(__name__)
router = Router()

# Timeout in seconds for Instagram API fetch — prevents bot freeze
_IG_TIMEOUT = 12

# In-memory rate-limit store: {user_id: [timestamp, ...]}
_link_rate_store: dict[int, list[float]] = {}


# ═══════════════════════════════════════
# FSM STATES
# ═══════════════════════════════════════

class WithdrawStates(StatesGroup):
    choosing_service = State()
    entering_link    = State()
    previewing       = State()
    entering_amount  = State()
    awaiting_proof   = State()


# ═══════════════════════════════════════
# RATE LIMITING HELPER
# ═══════════════════════════════════════

def _check_link_rate(user_id: int) -> bool:
    """Return True if user is within allowed rate, False if rate-limited."""
    import time
    now    = time.time()
    window = _link_rate_store.get(user_id, [])
    window = [t for t in window if now - t < LINK_RATE_WINDOW]
    if len(window) >= LINK_RATE_MAX:
        _link_rate_store[user_id] = window
        return False
    window.append(now)
    _link_rate_store[user_id] = window
    return True


# ═══════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════

async def _notify_admins_order_failed(
    bot: Bot, user_id: int, username: str,
    service: str, quantity: int, reason: str,
) -> None:
    try:
        admins    = await db.get_all_admins()
        admin_ids = list({MASTER_ADMIN_ID} | {a["user_id"] for a in admins})
        uname_str = f"@{username}" if username else f"ID {user_id}"
        text = (
            f"{e('error')} <b>Order Failed</b>\n{divider()}"
            f"{e('user')} {uname_str} (<code>{user_id}</code>)\n"
            f"{e('instagram')} {service} ×{quantity}\n{divider()}"
            f"Reason: {reason or 'Unknown'}"
        )
        for aid in admin_ids:
            try:
                await bot.send_message(aid, text, parse_mode="HTML")
            except Exception:
                pass
    except Exception as ex:
        logger.error(f"_notify_admins_order_failed uid={user_id}: {ex}")


async def _send_withdraw_screen(bot: Bot, chat_id: int, user_id: int):
    """Entry screen showing service menu."""
    try:
        user     = await db.get_user(user_id)
        if not user:
            return
        points   = round(user["points"], 2)
        min_pts  = float(await db.get_setting("min_withdraw_points", "10"))
        file_id  = await db.get_image("withdraw")

        if points < min_pts:
            caption = (
                f"{e('error')} <b>Not enough points</b>\n{divider()}"
                f"You need <b>{min_pts}</b> pts to order.\n"
                f"Your balance: <b>{points}</b> pts."
            )
            if file_id:
                await bot.send_photo(chat_id=chat_id, photo=file_id,
                                     caption=caption, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")
            return

        fol_pts = await db.get_setting("followers_points", "10")
        fol_amt = await db.get_setting("followers_amount", "100")
        lik_pts = await db.get_setting("likes_points", "5")
        lik_amt = await db.get_setting("likes_amount", "50")
        vie_pts = await db.get_setting("views_points", "3")
        vie_amt = await db.get_setting("views_amount", "100")
        com_pts = await db.get_setting("comments_points", "15")
        com_amt = await db.get_setting("comments_amount", "10")

        caption = (
            f"{e('withdraw')} <b>Withdraw</b>\n{divider()}"
            f"{e('points')} Balance: <b>{points} pts</b>\n{divider()}"
            f"{e('followers')} Followers — <code>{fol_pts}</code> pts → <code>{fol_amt}</code>\n"
            f"{e('likes')} Likes — <code>{lik_pts}</code> pts → <code>{lik_amt}</code>\n"
            f"{e('views')} Views — <code>{vie_pts}</code> pts → <code>{vie_amt}</code>\n"
            f"{e('comments')} Comments — <code>{com_pts}</code> pts → <code>{com_amt}</code>\n"
            f"{divider()}"
            f"{e('tip')} Choose a service below."
        )
        if file_id:
            await bot.send_photo(chat_id=chat_id, photo=file_id,
                                 caption=caption, parse_mode="HTML",
                                 reply_markup=withdraw_service_keyboard())
        else:
            await bot.send_message(chat_id=chat_id, text=caption,
                                   parse_mode="HTML",
                                   reply_markup=withdraw_service_keyboard())
    except Exception as ex:
        logger.error(f"_send_withdraw_screen uid={user_id}: {ex}", exc_info=True)


# ═══════════════════════════════════════
# ENTRY
# ═══════════════════════════════════════

# Exact match on button text
@router.message(F.text == BTN_WITHDRAW)
async def withdraw_handler(message: Message, bot: Bot, state: FSMContext):
    try:
        await state.clear()
        await _send_withdraw_screen(bot, message.chat.id, message.from_user.id)
    except Exception as ex:
        logger.error(f"withdraw_handler uid={message.from_user.id}: {ex}", exc_info=True)


@router.callback_query(F.data == "cancel_withdraw")
async def cb_cancel_withdraw(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
        await state.clear()
        await callback.message.answer(
            f"{e('cancel')} <b>Order cancelled.</b>",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as ex:
        logger.error(f"cb_cancel_withdraw uid={callback.from_user.id}: {ex}", exc_info=True)


# ═══════════════════════════════════════
# SERVICE SELECTION
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("withdraw_"))
async def cb_select_service(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
        service = callback.data.replace("withdraw_", "")

        sid = await db.get_setting(f"jap_{service}_service_id", "")
        if not sid and not jap.is_test_mode:
            await callback.message.answer(
                f"{e('error')} <b>Service not available right now.</b>\n"
                f"{e('tip')} Contact support.",
                parse_mode="HTML",
                reply_markup=error_keyboard(),
            )
            return

        user    = await db.get_user(callback.from_user.id)
        pts     = round(user["points"], 2) if user else 0
        svc_pts = float(await db.get_setting(f"{service}_points", "5"))
        if pts < svc_pts:
            await callback.message.answer(
                f"{e('error')} <b>Not enough points!</b>\n"
                f"Need: <b>{svc_pts}</b> pts  |  You have: <b>{pts}</b> pts",
                parse_mode="HTML",
                reply_markup=cancel_withdraw_keyboard(),
            )
            return

        scope = "single"
        if service in ("likes", "comments"):
            scope = await db.get_setting(f"jap_{service}_service_scope", "single")

        await state.set_state(WithdrawStates.entering_link)
        await state.update_data(service=service, scope=scope)

        if scope == "all" or service == "followers":
            prompt = (
                f"{e('instagram')} <b>Order {service.capitalize()}</b>\n"
                f"{divider()}"
                f"Send the <b>Instagram profile link</b> or <b>@username</b>.\n"
                f"{e('tip')} Example: <code>https://instagram.com/yourhandle</code>"
            )
        else:
            prompt = (
                f"{e('instagram')} <b>Order {service.capitalize()}</b>\n"
                f"{divider()}"
                f"Send the <b>post / reel link</b>.\n"
                f"{e('tip')} Example: <code>https://instagram.com/reel/ABC123/</code>"
            )

        await callback.message.answer(
            prompt, parse_mode="HTML",
            reply_markup=cancel_withdraw_keyboard(),
        )
    except Exception as ex:
        logger.error(f"cb_select_service uid={callback.from_user.id}: {ex}", exc_info=True)


# ═══════════════════════════════════════
# LINK RECEIVED — rate limit + duplicate guard + fetch Instagram preview
# ═══════════════════════════════════════

@router.message(WithdrawStates.entering_link)
async def handle_link_input(message: Message, state: FSMContext, bot: Bot):
    try:
        user_id = message.from_user.id
        data    = await state.get_data()
        service = data.get("service", "followers")
        scope   = data.get("scope", "single")
        link    = (message.text or "").strip()

        # ── Rate limiting on link/amount input ────────────────────────
        if not _check_link_rate(user_id):
            await message.answer(
                f"{e('warning')} <b>Slow down!</b>\n"
                f"You're submitting links too fast. Wait {LINK_RATE_WINDOW}s and try again.",
                parse_mode="HTML",
                reply_markup=cancel_withdraw_keyboard(),
            )
            return

        # ── Duplicate order guard ──────────────────────────────────────
        has_dupe = await db.has_recent_order(user_id, link, service, DUPLICATE_ORDER_WINDOW)
        if has_dupe:
            await message.answer(
                f"{e('warning')} <b>Duplicate order detected.</b>\n"
                f"You already placed a <b>{service}</b> order for this link recently.\n"
                f"{e('tip')} Wait a few minutes before ordering the same thing again.",
                parse_mode="HTML",
                reply_markup=cancel_withdraw_keyboard(),
            )
            return

        wait_msg = await message.answer(
            f"{e('loading')} <b>Fetching Instagram info…</b>\n"
            f"{e('tip')} <i>This takes a few seconds.</i>",
            parse_mode="HTML",
        )

        need_profile = (service == "followers") or (scope == "all")

        try:
            if need_profile or (not is_post_url(link)):
                info = await asyncio.wait_for(
                    fetch_profile_info(link),
                    timeout=_IG_TIMEOUT,
                )
                await _handle_profile_preview(
                    message, state, bot, wait_msg, info, service, link,
                )
            else:
                info = await asyncio.wait_for(
                    fetch_post_info(link),
                    timeout=_IG_TIMEOUT,
                )
                await _handle_post_preview(
                    message, state, bot, wait_msg, info, service, link,
                )
        except asyncio.TimeoutError:
            try:
                await wait_msg.delete()
            except Exception:
                pass
            await message.answer(
                f"{e('error')} <b>Instagram took too long to respond.</b>\n"
                f"{e('tip')} Check the link and try again.",
                parse_mode="HTML",
                reply_markup=cancel_withdraw_keyboard(),
            )
    except Exception as ex:
        logger.error(f"handle_link_input uid={message.from_user.id}: {ex}", exc_info=True)
        await state.clear()
        await message.answer(
            f"{e('error')} Something went wrong. Please try again.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )


async def _handle_profile_preview(
    message: Message, state: FSMContext, bot: Bot,
    wait_msg, info: dict, service: str, original_link: str,
):
    """Show profile preview for followers order (or all-scope likes/comments)."""
    try:
        await wait_msg.delete()
    except Exception:
        pass

    username = info.get("username") or clean_username(original_link)
    clean_link = f"https://www.instagram.com/{username}/"

    if not info.get("success"):
        caption = (
            f"{e('warning')} <b>Could not verify this profile.</b>\n"
            f"{e('tip')} Instagram sometimes blocks previews.\n"
            f"{divider()}"
            f"{e('instagram')} Username: <code>@{username}</code>\n"
            f"{e('link')} <code>{clean_link}</code>\n"
            f"{divider()}"
            f"Tap <b>Continue</b> to proceed, or <b>Cancel</b> to go back."
        )
        await state.update_data(instagram_link=clean_link, ig_username=username)
        await state.set_state(WithdrawStates.previewing)
        await message.answer(caption, parse_mode="HTML",
                             reply_markup=preview_continue_keyboard())
        return

    is_private  = info.get("is_private")
    followers   = _fmt_count(info.get("followers"))
    following   = _fmt_count(info.get("following"))
    posts       = _fmt_count(info.get("posts_count"))
    full_name   = info.get("full_name", username)
    bio         = (info.get("bio") or "").strip()[:100]
    pic_url     = info.get("profile_pic_url")

    caption = (
        f"{e('instagram')} <b>Instagram Profile</b>\n{divider()}"
        f"{e('user')} <b>{full_name}</b> (<code>@{username}</code>)\n"
    )
    if bio:
        caption += f"{e('tip')} <i>{bio}</i>\n"
    caption += (
        f"{divider()}"
        f"{e('followers')} Followers: <b>{followers}</b>\n"
        f"{e('refer_menu')} Following: <b>{following}</b>\n"
        f"{e('instagram')} Posts: <b>{posts}</b>\n"
        f"{divider()}"
    )
    if is_private:
        caption += (
            f"{e('warning')} <b>This account is private.</b>\n"
            f"Ordering for private accounts may fail or deliver 0.\n"
            f"{divider()}"
            f"You can still proceed — tap below."
        )
        await state.update_data(instagram_link=clean_link, ig_username=username)
        await state.set_state(WithdrawStates.previewing)
        if pic_url:
            try:
                await message.answer_photo(
                    photo=URLInputFile(pic_url, timeout=8),
                    caption=caption, parse_mode="HTML",
                    reply_markup=preview_private_keyboard(),
                )
                return
            except Exception:
                pass
        await message.answer(caption, parse_mode="HTML",
                             reply_markup=preview_private_keyboard())
        return

    caption += (
        f"{e('followers')} Ordering: <b>{service.capitalize()}</b>\n"
        f"{e('link')} <code>{clean_link}</code>\n"
        f"{divider()}"
        f"{e('tip')} Tap <b>Continue</b> to choose the amount."
    )
    await state.update_data(instagram_link=clean_link, ig_username=username)
    await state.set_state(WithdrawStates.previewing)

    if pic_url:
        try:
            await message.answer_photo(
                photo=URLInputFile(pic_url, timeout=8),
                caption=caption, parse_mode="HTML",
                reply_markup=preview_continue_keyboard(),
            )
            return
        except Exception:
            pass

    await message.answer(caption, parse_mode="HTML",
                         reply_markup=preview_continue_keyboard())


async def _handle_post_preview(
    message: Message, state: FSMContext, bot: Bot,
    wait_msg, info: dict, service: str, original_link: str,
):
    """Show reel/post preview for likes/views/comments orders."""
    try:
        await wait_msg.delete()
    except Exception:
        pass

    shortcode  = extract_shortcode(original_link) or ""
    clean_link = (
        f"https://www.instagram.com/reel/{shortcode}/"
        if shortcode else original_link
    )

    if not info.get("success"):
        caption = (
            f"{e('warning')} <b>Could not verify this reel.</b>\n"
            f"{e('tip')} Instagram sometimes blocks previews.\n"
            f"{divider()}"
            f"{e('link')} Link: <code>{clean_link}</code>\n"
            f"{divider()}"
            f"Tap <b>Continue</b> to proceed anyway, or <b>Cancel</b> to go back."
        )
        await state.update_data(instagram_link=clean_link)
        await state.set_state(WithdrawStates.previewing)
        await message.answer(caption, parse_mode="HTML",
                             reply_markup=preview_continue_keyboard())
        return

    username      = info.get("username", "")
    caption_text  = (info.get("caption") or "").strip()[:120]
    like_count    = _fmt_count(info.get("like_count"))
    comment_count = _fmt_count(info.get("comment_count"))
    view_count    = _fmt_count(info.get("view_count"))
    thumbnail_url = info.get("thumbnail_url")

    svc_emoji = {"likes": e("likes"), "comments": e("comments"), "views": e("views")}.get(service, e("instagram"))

    caption = f"{e('instagram')} <b>Reel Preview</b>\n{divider()}"
    if username:
        caption += f"{e('user')} <b>@{username}</b>\n"
    if caption_text:
        caption += f"{e('tip')} <i>{caption_text}</i>\n"
    caption += f"{divider()}"
    if like_count != "N/A":
        caption += f"{e('likes')} Likes: <b>{like_count}</b>\n"
    if comment_count != "N/A":
        caption += f"{e('comments')} Comments: <b>{comment_count}</b>\n"
    if view_count != "N/A":
        caption += f"{e('views')} Views: <b>{view_count}</b>\n"
    caption += (
        f"{divider()}"
        f"{svc_emoji} Ordering: <b>{service.capitalize()}</b>\n"
        f"{e('link')} <code>{clean_link}</code>\n"
        f"{divider()}"
        f"{e('tip')} Tap <b>Continue</b> to choose the amount."
    )

    await state.update_data(instagram_link=clean_link, ig_username=username)
    await state.set_state(WithdrawStates.previewing)

    if thumbnail_url:
        try:
            await message.answer_photo(
                photo=URLInputFile(thumbnail_url, timeout=8),
                caption=caption, parse_mode="HTML",
                reply_markup=preview_continue_keyboard(),
            )
            return
        except Exception:
            pass

    await message.answer(caption, parse_mode="HTML",
                         reply_markup=preview_continue_keyboard())


# ═══════════════════════════════════════
# CONTINUE — ASK FOR AMOUNT
# ═══════════════════════════════════════

@router.callback_query(F.data == "preview_continue", WithdrawStates.previewing)
async def cb_preview_continue(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
        data    = await state.get_data()
        service = data.get("service", "followers")
        user    = await db.get_user(callback.from_user.id)
        pts     = round(user["points"], 2) if user else 0

        svc_pts = float(await db.get_setting(f"{service}_points", "5"))
        svc_amt = int(await db.get_setting(f"{service}_amount", "50"))
        if svc_amt <= 0:
            svc_amt = 1
        max_batches = int(pts // svc_pts) if svc_pts > 0 else 0
        max_order   = max_batches * svc_amt

        if max_order <= 0:
            await callback.message.answer(
                f"{e('error')} Not enough points for even 1 batch.\n"
                f"Earn more points first!",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            await state.clear()
            return

        await state.update_data(svc_pts=svc_pts, svc_amt=svc_amt, max_order=max_order)
        await state.set_state(WithdrawStates.entering_amount)

        await callback.message.answer(
            f"{e('points')} <b>How many {service.lower()} do you want?</b>\n"
            f"{divider()}"
            f"{e('tip')} You have <b>{pts} pts</b>\n"
            f"{e('balance')} Ratio: <code>{svc_pts} pts</code> = <code>{svc_amt} {service}</code>\n"
            f"{e('star')} Max you can order: <b>{max_order}</b>\n"
            f"{divider()}"
            f"Enter a number (multiples of <code>{svc_amt}</code>):",
            parse_mode="HTML",
            reply_markup=cancel_withdraw_keyboard(),
        )
    except Exception as ex:
        logger.error(f"cb_preview_continue uid={callback.from_user.id}: {ex}", exc_info=True)


# ═══════════════════════════════════════
# AMOUNT RECEIVED — PLACE ORDER
# ═══════════════════════════════════════

@router.message(WithdrawStates.entering_amount)
async def handle_amount_input(message: Message, state: FSMContext, bot: Bot):
    try:
        user_id   = message.from_user.id
        data      = await state.get_data()
        service   = data.get("service", "followers")
        ig_link   = data.get("instagram_link", "")
        svc_pts   = data.get("svc_pts", 5.0)
        svc_amt   = data.get("svc_amt", 50)
        max_order = data.get("max_order", 0)

        try:
            qty = int(message.text.strip().replace(",", "").replace(".", ""))
        except ValueError:
            await message.answer(
                f"{e('error')} Enter a valid number.", parse_mode="HTML",
            )
            return

        if qty <= 0:
            await message.answer(f"{e('error')} Amount must be positive.", parse_mode="HTML")
            return

        qty = max(svc_amt, round(qty / svc_amt) * svc_amt)

        if qty > max_order:
            await message.answer(
                f"{e('error')} Maximum you can order is <b>{max_order}</b>.\n"
                f"Enter a smaller amount.",
                parse_mode="HTML",
            )
            return

        batches    = qty // svc_amt
        pts_needed = batches * svc_pts

        user = await db.get_user(user_id)
        pts  = round(user["points"], 2) if user else 0
        if pts < pts_needed:
            await message.answer(
                f"{e('error')} Not enough points!\n"
                f"Need: <b>{pts_needed}</b> pts  |  Have: <b>{pts}</b> pts",
                parse_mode="HTML",
            )
            return

        service_id = await db.get_setting(f"jap_{service}_service_id", "")
        wait_msg   = await message.answer(
            f"{e('loading')} <b>Placing your order…</b>", parse_mode="HTML",
        )

        jap_id = await jap.place_order(service_id, ig_link, qty)

        try:
            await wait_msg.delete()
        except Exception:
            pass

        if not jap_id:
            await state.clear()
            await _notify_admins_order_failed(
                bot, user_id,
                message.from_user.username or "", service, qty,
                "JAP place_order returned None",
            )
            await message.answer(
                f"{e('error')} <b>Order failed!</b>\n"
                f"The panel rejected the request. Please try again later.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            return

        # Deduct points & save order
        await db.deduct_points(user_id, pts_needed)
        order_id = await db.create_order(
            user_id=user_id,
            service=service,
            quantity=qty,
            instagram_link=ig_link,
            points_spent=pts_needed,
            jap_order_id=jap_id,
        )

        await state.set_state(WithdrawStates.awaiting_proof)
        await state.update_data(order_id=order_id, qty=qty, service=service, jap_id=jap_id)

        new_bal = round((user["points"] - pts_needed), 2)
        await message.answer(
            f"{e('success')} <b>Order Placed!</b>\n{divider()}"
            f"{e('instagram')} Service: <b>{service.capitalize()}</b>\n"
            f"{e('followers')} Quantity: <b>{qty}</b>\n"
            f"{e('link')} <code>{ig_link}</code>\n"
            f"{e('points')} Cost: <b>{pts_needed} pts</b>\n"
            f"{e('balance')} Remaining: <b>{new_bal} pts</b>\n"
            f"{e('key')} Order ID: <code>#{jap_id}</code>\n"
            f"{divider()}"
            f"{e('tip')} Send a screenshot as proof, or skip below.",
            parse_mode="HTML",
            reply_markup=skip_proof_keyboard(),
        )
    except Exception as ex:
        logger.error(f"handle_amount_input uid={message.from_user.id}: {ex}", exc_info=True)
        await state.clear()
        await message.answer(
            f"{e('error')} Something went wrong. Please try again.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )


# ═══════════════════════════════════════
# PROOF SUBMISSION
# ═══════════════════════════════════════

@router.callback_query(F.data == "skip_proof", WithdrawStates.awaiting_proof)
async def cb_skip_proof(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
        data     = await state.get_data()
        order_id = data.get("order_id", "")
        jap_id   = data.get("jap_id", "")
        await state.clear()
        await callback.message.answer(
            f"{e('success')} <b>Order submitted!</b>\n"
            f"{e('key')} Order ID: <code>#{jap_id}</code>\n"
            f"{e('loading')} Processing — check back soon.",
            parse_mode="HTML",
            reply_markup=check_order_keyboard(order_id),
        )
    except Exception as ex:
        logger.error(f"cb_skip_proof uid={callback.from_user.id}: {ex}", exc_info=True)


@router.message(WithdrawStates.awaiting_proof)
async def handle_proof_photo(message: Message, state: FSMContext, bot: Bot):
    try:
        data     = await state.get_data()
        order_id = data.get("order_id", "")
        jap_id   = data.get("jap_id", "")
        await state.clear()

        proof_ch = await db.get_setting("proof_channel_id", "")
        if proof_ch and message.photo:
            try:
                await bot.forward_message(
                    chat_id=int(proof_ch),
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            except Exception as ex:
                logger.warning(f"forward proof: {ex}")

        await message.answer(
            f"{e('success')} <b>Order submitted with proof!</b>\n"
            f"{e('key')} Order ID: <code>#{jap_id}</code>\n"
            f"{e('loading')} Processing — check back soon.",
            parse_mode="HTML",
            reply_markup=check_order_keyboard(order_id),
        )
    except Exception as ex:
        logger.error(f"handle_proof_photo uid={message.from_user.id}: {ex}", exc_info=True)
        await state.clear()


# ═══════════════════════════════════════
# ORDER STATUS CHECK  (with auto-refund)
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("check_order_"))
async def cb_check_order(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer(f"{e('loading')} Checking…", show_alert=False)
        order_id = callback.data.replace("check_order_", "")
        order    = await db.get_order(order_id)
        if not order:
            await callback.message.answer(
                f"{e('error')} Order not found.", parse_mode="HTML",
            )
            return

        status_info = await jap.check_status(order["jap_order_id"])
        if status_info:
            new_status = status_info["status"]
            remains    = status_info.get("remains", "?")
            await db.update_order_status(order_id, new_status)
            status     = new_status
        else:
            status  = order["status"]
            remains = "?"

        # ── Auto-refund safety net on manual check ────────────────────
        # (background checker also does this, but user might check before it runs)
        if status in ("Cancelled", "Failed", "cancelled", "failed"):
            pts_spent = order.get("points_spent", 0)
            if pts_spent and pts_spent > 0 and not order.get("refunded"):
                await db.add_points(order["user_id"], pts_spent)
                await db.mark_order_refunded(order_id)
                try:
                    await bot.send_message(
                        order["user_id"],
                        f"{e('bonus')} <b>Order refunded!</b>\n"
                        f"Order <code>#{order['jap_order_id']}</code> was {status}.\n"
                        f"{e('points')} <b>+{pts_spent} pts</b> returned to your balance.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        SEV = {
            "Completed":   e("success"), "completed":   e("success"),
            "In progress": e("loading"), "processing":  e("loading"),
            "pending":     e("pending"),
            "Partial":     e("warning"),
            "Cancelled":   e("error"),   "Failed": e("error"),
            "cancelled":   e("error"),   "failed": e("error"),
        }
        sev = SEV.get(status, e("loading"))

        text = (
            f"{e('botstats')} <b>Order Status</b>\n{divider()}"
            f"Order <code>#{order['jap_order_id']}</code>  |  "
            f"{order['service'].capitalize()} ×{order['quantity']}\n"
            f"{e('link')} <code>{order['instagram_link']}</code>\n{divider()}"
            f"{sev} <b>{status}</b>  |  Remains: <code>{remains}</code>"
        )
        try:
            await callback.message.edit_caption(text, parse_mode="HTML",
                                                reply_markup=check_order_keyboard(order_id))
        except Exception:
            try:
                await callback.message.edit_text(text, parse_mode="HTML",
                                                 reply_markup=check_order_keyboard(order_id))
            except Exception:
                await callback.message.answer(text, parse_mode="HTML",
                                              reply_markup=check_order_keyboard(order_id))
    except Exception as ex:
        logger.error(f"cb_check_order uid={callback.from_user.id}: {ex}", exc_info=True)
