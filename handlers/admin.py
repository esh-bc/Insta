"""
handlers/admin.py — Full admin panel.
Fixed: channel management, add/remove without errors, clear channel DB.
New:  Super Control (logs, reboot, token change, latest push), maintenance mode,
      service scope (single post vs all posts), @notnow1122 support.
Master admin: @iam_esh — immutable.
"""

import asyncio
import io
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone, timedelta

import psutil
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    BufferedInputFile,
)

import database as db
from api.jap import jap
from config import BOT_NAME, MASTER_ADMIN_ID, SCREENS, JAP_BASE_URL, GITHUB_REPO_URL
from emojis import e, divider, update_override, PREMIUM
from keyboards import (
    admin_panel_keyboard, admin_stats_keyboard, admin_system_keyboard,
    admin_panel_details_keyboard, admin_force_sub_keyboard,
    admin_image_manager_keyboard, admin_image_actions_keyboard,
    admin_ban_keyboard, admin_bonus_keyboard, admin_admins_keyboard,
    admin_settings_keyboard, admin_pending_orders_keyboard,
    admin_order_detail_keyboard, admin_captcha_keyboard,
    back_keyboard, error_keyboard, main_menu_keyboard,
    admin_api_config_keyboard, admin_proof_channel_keyboard,
    admin_messages_keyboard, admin_messages_confirm_reset_keyboard,
    maintenance_keyboard, super_control_keyboard,
    sc_confirm_reboot_keyboard, sc_push_confirm_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()

BOT_START_TIME = datetime.now(timezone.utc)


# ═══════════════════════════════════════
# FSM STATES
# ═══════════════════════════════════════

class AdminStates(StatesGroup):
    broadcast_msg            = State()
    add_channel_display_name = State()
    add_channel_link         = State()
    add_channel_id           = State()
    set_service_id           = State()
    set_service_scope        = State()
    set_min_points           = State()
    set_refer_points         = State()
    set_followers_ratio      = State()
    set_likes_ratio          = State()
    set_views_ratio          = State()
    set_comments_ratio       = State()
    ban_user                 = State()
    unban_user               = State()
    add_admin                = State()
    remove_admin             = State()
    give_bonus_user          = State()
    give_bonus_amount        = State()
    give_bonus_all           = State()
    create_code_name         = State()
    create_code_points       = State()
    create_code_uses         = State()
    create_code_expiry       = State()
    delete_code              = State()
    upload_image_waiting     = State()
    set_proofs_channel       = State()
    set_api_key              = State()
    set_api_url              = State()
    proof_channel_id_input   = State()
    proof_channel_link_input = State()
    edit_promo_msg           = State()
    edit_menu_msg            = State()
    # Super Control states
    sc_new_token             = State()
    sc_test_token            = State()
    sc_confirm_push_state    = State()


# ═══════════════════════════════════════
# PERMISSION HELPERS
# ═══════════════════════════════════════

async def check_admin(user_id: int) -> bool:
    return await db.is_admin(user_id, MASTER_ADMIN_ID)


def is_master(user_id: int) -> bool:
    return user_id == MASTER_ADMIN_ID


# ═══════════════════════════════════════
# ADMIN PANEL ENTRY
# ═══════════════════════════════════════

async def send_admin_panel(bot: Bot, chat_id: int, user_id: int = 0):
    master = is_master(user_id)
    maint  = await db.is_maintenance()
    maint_str = f"  {e('maintenance')} <b>MAINTENANCE ON</b>" if maint else ""
    text = (
        f"{e('crown')} <b>ADMIN PANEL</b>{maint_str}\n"
        f"{divider()}"
        f"{e('tip')} Choose a section below."
    )
    try:
        await bot.send_message(
            chat_id, text, parse_mode="HTML",
            reply_markup=admin_panel_keyboard(is_master=master),
        )
    except Exception as ex:
        logger.error(f"send_admin_panel: {ex}", exc_info=True)


@router.message(Command("admin"))
async def cmd_admin(message: Message, bot: Bot, state: FSMContext):
    try:
        if not await check_admin(message.from_user.id):
            await message.answer(
                f"{e('error')} <b>Access Denied!</b>", parse_mode="HTML",
            )
            return
        await state.clear()
        await send_admin_panel(bot, message.chat.id, message.from_user.id)
    except Exception as ex:
        logger.error(f"cmd_admin: {ex}", exc_info=True)


@router.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery, bot: Bot, state: FSMContext):
    try:
        await callback.answer()
        await state.clear()
        await send_admin_panel(bot, callback.message.chat.id, callback.from_user.id)
    except Exception as ex:
        logger.error(f"cb_admin_back: {ex}", exc_info=True)


# ═══════════════════════════════════════
# STATS
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        total_users  = await db.get_user_count()
        pending_ords = await db.get_pending_orders()
        all_ords     = await db.get_all_orders(1000)
        done_count   = sum(1 for o in all_ords if o.get("status", "").lower() in ("completed", "complete"))
        balance      = await jap.get_balance() or "N/A"
        maint        = await db.is_maintenance()

        text = (
            f"{e('botstats')} <b>BOT STATS</b>\n{divider()}"
            f"{e('user')} Users: <b>{total_users}</b>\n"
            f"{e('stock')} Total Orders: <b>{len(all_ords)}</b>\n"
            f"{e('pending')} Pending: <b>{len(pending_ords)}</b>\n"
            f"{e('success')} Completed: <b>{done_count}</b>\n"
            f"{e('balance')} JAP Balance: <b>${balance}</b>\n"
            f"{e('maintenance')} Maintenance: <b>{'ON' if maint else 'OFF'}</b>\n"
            f"{divider()}"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=admin_stats_keyboard())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=admin_stats_keyboard())
    except Exception as ex:
        logger.error(f"cb_admin_stats: {ex}", exc_info=True)


# ═══════════════════════════════════════
# SYSTEM INFO
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_system")
async def cb_admin_system(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        uptime = datetime.now(timezone.utc) - BOT_START_TIME
        hours, rem = divmod(int(uptime.total_seconds()), 3600)
        mins        = rem // 60

        cpu  = psutil.cpu_percent(interval=0.5)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        text = (
            f"{e('system')} <b>SYSTEM INFO</b>\n{divider()}"
            f"{e('botstats')} Uptime: <b>{hours}h {mins}m</b>\n"
            f"{e('stats')} CPU: <b>{cpu:.1f}%</b>\n"
            f"{e('balance')} RAM: <b>{ram.percent:.1f}%</b> "
            f"(<code>{ram.used // 1024**2}</code> / "
            f"<code>{ram.total // 1024**2}</code> MB)\n"
            f"{e('stock')} Disk: <b>{disk.percent:.1f}%</b>\n"
            f"{e('star')} Python: <b>{platform.python_version()}</b>\n"
            f"{e('system')} OS: <b>{platform.system()} {platform.release()}</b>\n"
            f"{divider()}"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=admin_system_keyboard())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=admin_system_keyboard())
    except Exception as ex:
        logger.error(f"cb_admin_system: {ex}", exc_info=True)


# ═══════════════════════════════════════
# PANEL DETAILS (JAP service IDs + prices)
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_panel_details")
async def cb_panel_details(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return

        balance = await jap.get_balance() or "N/A"
        sids = {
            svc: await db.get_setting(f"jap_{svc}_service_id", "") or ""
            for svc in ("followers", "likes", "views", "comments")
        }
        scopes = {
            svc: await db.get_setting(f"jap_{svc}_service_scope", "single")
            for svc in ("likes", "comments")
        }

        services_list = await jap.get_services() or []
        _svc_map = {str(s.get("service", "")): s for s in services_list}

        def _price(sid: str) -> str:
            if not sid:
                return "N/A"
            s = _svc_map.get(str(sid))
            return f"${s['rate']}/1k" if s and s.get("rate") else "N/A"

        def _sid_fmt(sid: str) -> str:
            return f"<code>{sid}</code>" if sid else "<i>Not Set</i>"

        def _scope_badge(svc: str) -> str:
            scope = scopes.get(svc, "single")
            return f"({scope})" if scope else ""

        text = (
            f"{e('panel')} <b>JAP PANEL DETAILS</b>\n{divider()}"
            f"{e('balance')} Balance: <b>${balance}</b>\n{divider()}"
            f"{e('followers')} <b>Followers</b>  ID: {_sid_fmt(sids['followers'])}"
            f"  Price: <b>{_price(sids['followers'])}</b>\n"
            f"{e('likes')} <b>Likes</b>  ID: {_sid_fmt(sids['likes'])}"
            f"  Price: <b>{_price(sids['likes'])}</b>  {_scope_badge('likes')}\n"
            f"{e('views')} <b>Views</b>  ID: {_sid_fmt(sids['views'])}"
            f"  Price: <b>{_price(sids['views'])}</b>\n"
            f"{e('comments')} <b>Comments</b>  ID: {_sid_fmt(sids['comments'])}"
            f"  Price: <b>{_price(sids['comments'])}</b>  {_scope_badge('comments')}\n"
            f"{divider()}"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=admin_panel_details_keyboard())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=admin_panel_details_keyboard())
    except Exception as ex:
        logger.error(f"cb_panel_details: {ex}", exc_info=True)


# ─── Set service ID (with scope question for likes/comments) ─────────────────

@router.callback_query(F.data.startswith("admin_set_service_"))
async def cb_set_service_id(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        svc = callback.data.replace("admin_set_service_", "")
        await state.set_state(AdminStates.set_service_id)
        await state.update_data(service_name=svc)
        await callback.message.answer(
            f"{e('settings')} <b>Enter Service ID for <i>{svc}</i>:</b>\n"
            f"{divider()}"
            f"{e('tip')} Find your service ID from the JAP panel.",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_panel_details"),
        )
    except Exception as ex:
        logger.error(f"cb_set_service_id: {ex}", exc_info=True)


@router.message(AdminStates.set_service_id)
async def handle_set_service_id(message: Message, state: FSMContext, bot: Bot):
    try:
        data = await state.get_data()
        svc  = data["service_name"]
        val  = message.text.strip()

        await db.set_setting(f"jap_{svc}_service_id", val)
        await db.log_admin_action(f"set_service_id:{svc}={val}", message.from_user.id)

        # For likes and comments, ask about scope
        if svc in ("likes", "comments"):
            await state.set_state(AdminStates.set_service_scope)
            await state.update_data(service_name=svc, service_id=val)

            from keyboards import service_scope_keyboard
            await message.answer(
                f"{e('success')} Service ID <code>{val}</code> saved for <b>{svc}</b>.\n"
                f"{divider()}"
                f"{e('tip')} <b>Does this service send {svc} to a single post or all posts on an account?</b>\n\n"
                f"<blockquote>"
                f"{e('single_post')} <b>Single Post</b> — user provides a specific post/reel URL\n"
                f"{e('all_posts')} <b>All Posts</b> — user provides their profile URL (service distributes {svc} across all posts)"
                f"</blockquote>",
                parse_mode="HTML",
                reply_markup=service_scope_keyboard(svc),
            )
        else:
            await state.clear()
            await message.answer(
                f"{e('success')} Service ID for <b>{svc}</b> set to <code>{val}</code>",
                parse_mode="HTML",
                reply_markup=back_keyboard("admin_panel_details"),
            )
    except Exception as ex:
        logger.error(f"handle_set_service_id: {ex}", exc_info=True)


@router.callback_query(F.data.startswith("scope_"))
async def cb_set_scope(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
        parts = callback.data.split("_", 2)  # scope_{single/all}_{svc}
        scope = parts[1]
        svc   = parts[2] if len(parts) > 2 else ""
        if not svc:
            await state.clear()
            return
        await db.set_setting(f"jap_{svc}_service_scope", scope)
        await db.log_admin_action(f"set_service_scope:{svc}={scope}", callback.from_user.id)
        await state.clear()
        scope_label = "All Posts on Account" if scope == "all" else "Single Post / Reel"
        await callback.message.answer(
            f"{e('success')} <b>{svc.capitalize()} scope set to:</b> {scope_label}\n"
            f"{divider()}"
            f"{e('tip')} Users will now be asked for a "
            f"{'<b>profile link</b>' if scope == 'all' else '<b>post/reel link</b>'}.",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_panel_details"),
        )
    except Exception as ex:
        logger.error(f"cb_set_scope: {ex}", exc_info=True)


# ═══════════════════════════════════════
# FORCE SUBSCRIPTION CHANNELS  (fully fixed)
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_force_sub")
async def cb_admin_force_sub(callback: CallbackQuery, bot: Bot, state: FSMContext):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        await state.clear()
        channels = await db.get_all_channels()
        text = (
            f"{e('channel')} <b>FORCE SUBSCRIPTION</b>\n{divider()}"
            f"{e('followers')} Active channels: <b>{len(channels)}</b>\n"
            f"{divider()}"
        )
        if channels:
            for ch in channels:
                display = ch.get("display_name") or ch.get("channel_username", "?")
                cid     = ch.get("channel_id", "?")
                text += f"{e('check')} <b>{display}</b>  (<code>{cid}</code>)\n"
        else:
            text += f"{e('tip')} No channels configured. Add one to enable force-join.\n"
        text += divider()
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=admin_force_sub_keyboard(channels))
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=admin_force_sub_keyboard(channels))
    except Exception as ex:
        logger.error(f"cb_admin_force_sub: {ex}", exc_info=True)


# ─── Add channel (3-step wizard) ─────────────────────────────────────────────

@router.callback_query(F.data == "admin_add_channel")
async def cb_add_channel(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        await state.set_state(AdminStates.add_channel_display_name)
        await callback.message.answer(
            f"{e('channel')} <b>Add Channel — Step 1 of 3</b>\n{divider()}"
            f"Enter the <b>display name</b> for the channel button.\n"
            f"{e('tip')} Example: <code>My Channel</code>",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_force_sub"),
        )
    except Exception as ex:
        logger.error(f"cb_add_channel: {ex}", exc_info=True)


@router.message(AdminStates.add_channel_display_name)
async def handle_channel_display_name(message: Message, state: FSMContext):
    try:
        display_name = message.text.strip()
        if len(display_name) < 1:
            await message.answer(f"{e('error')} Display name cannot be empty.", parse_mode="HTML")
            return
        await state.update_data(display_name=display_name)
        await state.set_state(AdminStates.add_channel_link)
        await message.answer(
            f"{e('link')} <b>Add Channel — Step 2 of 3</b>\n{divider()}"
            f"Enter the channel's <b>invite link</b> or <b>t.me URL</b>.\n"
            f"{e('tip')} Example: <code>https://t.me/mychannel</code>",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_force_sub"),
        )
    except Exception as ex:
        logger.error(f"handle_channel_display_name: {ex}", exc_info=True)


@router.message(AdminStates.add_channel_link)
async def handle_channel_link(message: Message, state: FSMContext):
    try:
        channel_link = message.text.strip()
        if not (channel_link.startswith("http") or channel_link.startswith("@")):
            await message.answer(
                f"{e('warning')} Enter a valid URL like <code>https://t.me/mychannel</code>",
                parse_mode="HTML",
            )
            return
        await state.update_data(channel_link=channel_link)
        await state.set_state(AdminStates.add_channel_id)
        await message.answer(
            f"{e('id')} <b>Add Channel — Step 3 of 3</b>\n{divider()}"
            f"Enter the channel's <b>numeric Telegram ID</b> or <b>@username</b>.\n"
            f"{e('tip')} Examples:\n"
            f"  • <code>-1001234567890</code> (private channel)\n"
            f"  • <code>@mychannel</code> (public channel)\n"
            f"{e('warning')} The bot must be an admin in the channel.",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_force_sub"),
        )
    except Exception as ex:
        logger.error(f"handle_channel_link: {ex}", exc_info=True)


@router.message(AdminStates.add_channel_id)
async def handle_channel_id(message: Message, bot: Bot, state: FSMContext):
    try:
        raw = message.text.strip()

        # Parse channel reference
        if raw.lstrip("-").isdigit():
            channel_ref = int(raw)
        elif raw.startswith("@") or not raw.startswith("-"):
            channel_ref = raw if raw.startswith("@") else f"@{raw}"
        else:
            await message.answer(
                f"{e('error')} Invalid channel ID. Use <code>-1001234567890</code> or <code>@username</code>",
                parse_mode="HTML",
            )
            return

        # ── Check bot is admin ───────────────────────────────────────
        wait_msg = await message.answer(
            f"{e('loading')} <b>Checking bot admin rights…</b>", parse_mode="HTML",
        )
        try:
            bot_user = await bot.get_me()
            member   = await bot.get_chat_member(chat_id=channel_ref, user_id=bot_user.id)
        except Exception as ex:
            try:
                await wait_msg.delete()
            except Exception:
                pass
            await message.answer(
                f"{e('error')} <b>Cannot access the channel.</b>\n{divider()}"
                f"Make sure:\n"
                f"• The channel ID / username is correct\n"
                f"• The bot has been added to the channel\n\n"
                f"Error: <code>{ex}</code>",
                parse_mode="HTML",
                reply_markup=back_keyboard("admin_force_sub"),
            )
            return

        if member.status not in ("administrator", "creator"):
            try:
                await wait_msg.delete()
            except Exception:
                pass
            await message.answer(
                f"{e('error')} <b>Bot is not an admin in this channel!</b>\n{divider()}"
                f"Add the bot as admin, then try again.",
                parse_mode="HTML",
                reply_markup=back_keyboard("admin_force_sub"),
            )
            await state.clear()
            return

        # ── Fetch channel info ───────────────────────────────────────
        try:
            chat_info  = await bot.get_chat(channel_ref)
            numeric_id = chat_info.id
            username   = (chat_info.username or "").lstrip("@")
        except Exception:
            numeric_id = channel_ref if isinstance(channel_ref, int) else 0
            username   = raw.lstrip("@") if not raw.lstrip("-").isdigit() else ""

        data         = await state.get_data()
        display_name = data.get("display_name", username or "Channel")
        channel_link = data.get("channel_link", "")

        await db.add_channel(
            channel_id=numeric_id,
            channel_username=username,
            display_name=display_name,
            channel_link=channel_link,
        )
        await db.log_admin_action(
            f"add_channel:{display_name}:{numeric_id}", message.from_user.id,
        )
        await state.clear()

        try:
            await wait_msg.delete()
        except Exception:
            pass

        await message.answer(
            f"{e('success')} <b>Channel added!</b>\n{divider()}"
            f"{e('channel')} <b>{display_name}</b>\n"
            f"{e('id')} ID: <code>{numeric_id}</code>",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_force_sub"),
        )
    except Exception as ex:
        logger.error(f"handle_channel_id: {ex}", exc_info=True)
        await state.clear()
        await message.answer(
            f"{e('error')} Failed to add channel: <code>{ex}</code>",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_force_sub"),
        )


# ─── Remove channel ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_remove_channel_"))
async def cb_remove_channel(callback: CallbackQuery, bot: Bot, state: FSMContext):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        cid_str = callback.data.replace("admin_remove_channel_", "")
        try:
            cid = int(cid_str)
        except ValueError:
            cid = 0

        if cid:
            removed = await db.remove_channel(cid)
        else:
            removed = False

        await db.log_admin_action(f"remove_channel:{cid}", callback.from_user.id)

        # Refresh the force-sub panel
        channels = await db.get_all_channels()

        # If no channels left — reset all users' verified status
        if not channels:
            await db.col("users").update_many({}, {"$set": {"is_verified": 0}})

        msg_text = (
            f"{e('success')} <b>Channel removed!</b>\n{divider()}"
            f"{e('followers')} Remaining channels: <b>{len(channels)}</b>"
        )
        if not channels:
            msg_text += f"\n{e('tip')} All channels removed — verification reset for all users."

        await callback.message.answer(
            msg_text, parse_mode="HTML",
            reply_markup=admin_force_sub_keyboard(channels),
        )
    except Exception as ex:
        logger.error(f"cb_remove_channel: {ex}", exc_info=True)


# ─── Clear all channels ───────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_clear_channels")
async def cb_clear_channels(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        count = await db.clear_all_channels()
        await db.log_admin_action("clear_all_channels", callback.from_user.id)
        await callback.message.answer(
            f"{e('success')} <b>All channels cleared!</b>\n{divider()}"
            f"{e('refresh')} <b>{count}</b> channel(s) removed.\n"
            f"{e('tip')} All users' verification has been reset — they'll re-verify next /start.",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_force_sub"),
        )
    except Exception as ex:
        logger.error(f"cb_clear_channels: {ex}", exc_info=True)


# ═══════════════════════════════════════
# MAINTENANCE MODE
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_maintenance")
async def cb_admin_maintenance(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        maint = await db.is_maintenance()
        text = (
            f"{e('maintenance')} <b>MAINTENANCE MODE</b>\n{divider()}"
            f"Status: <b>{'ON — bot is in maintenance' if maint else 'OFF — bot is running normally'}</b>\n"
            f"{divider()}"
            f"{e('tip')} When maintenance is ON, only admins can use the bot."
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=maintenance_keyboard(maint))
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=maintenance_keyboard(maint))
    except Exception as ex:
        logger.error(f"cb_admin_maintenance: {ex}", exc_info=True)


@router.callback_query(F.data == "maintenance_toggle")
async def cb_maintenance_toggle(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        current = await db.is_maintenance()
        await db.set_maintenance(not current)
        await db.log_admin_action(
            f"maintenance_toggle:{'off' if current else 'on'}", callback.from_user.id,
        )
        new_state = not current
        status_txt = "ON — bot is now in maintenance" if new_state else "OFF — bot is running normally"
        await callback.message.answer(
            f"{e('maintenance') if new_state else e('success')} <b>Maintenance {status_txt}</b>",
            parse_mode="HTML",
            reply_markup=maintenance_keyboard(new_state),
        )
    except Exception as ex:
        logger.error(f"cb_maintenance_toggle: {ex}", exc_info=True)


# ═══════════════════════════════════════
# SUPER CONTROL  (master admin only)
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_super_control")
async def cb_super_control(callback: CallbackQuery, bot: Bot, state: FSMContext):
    try:
        await callback.answer()
        if not is_master(callback.from_user.id):
            await callback.answer("Master admin only!", show_alert=True)
            return
        await state.clear()
        text = (
            f"{e('super')} <b>SUPER CONTROL</b>\n{divider()}"
            f"{e('tip')} Full bot management from here.\n"
            f"Only <b>@iam_esh</b> has access to this panel.\n"
            f"{divider()}"
            f"{e('logs')} Live Logs — last 100 log lines as TXT\n"
            f"{e('reboot')} Soft Reboot — gracefully restart the bot\n"
            f"{e('token')} Change Token — hot-swap bot token without SSH\n"
            f"{e('github')} Latest Push — pull & test before deploying\n"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=super_control_keyboard())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=super_control_keyboard())
    except Exception as ex:
        logger.error(f"cb_super_control: {ex}", exc_info=True)


# ─── Logs ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sc_logs")
async def cb_sc_logs(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not is_master(callback.from_user.id):
            return

        # Get in-memory log buffer (populated by LogBufferHandler in main.py)
        from main import _LOG_BUFFER
        lines = list(_LOG_BUFFER)

        if not lines:
            await callback.message.answer(
                f"{e('logs')} No logs captured yet. Buffer fills as the bot runs.",
                parse_mode="HTML",
                reply_markup=back_keyboard("admin_super_control"),
            )
            return

        ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        txt = f"═══ BOT LOGS — Last {len(lines)} lines — {ts} ═══\n\n"
        txt += "\n".join(lines)

        doc = BufferedInputFile(txt.encode("utf-8"), filename=f"bot_logs_{ts[:10]}.txt")
        await callback.message.answer_document(
            doc,
            caption=f"{e('logs')} <b>Live Logs</b> — last <b>{len(lines)}</b> lines",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_super_control"),
        )
    except Exception as ex:
        logger.error(f"cb_sc_logs: {ex}", exc_info=True)
        await callback.message.answer(
            f"{e('error')} Failed to retrieve logs: <code>{ex}</code>",
            parse_mode="HTML",
        )


# ─── Soft Reboot ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sc_reboot")
async def cb_sc_reboot(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not is_master(callback.from_user.id):
            return
        text = (
            f"{e('reboot')} <b>Soft Reboot</b>\n{divider()}"
            f"{e('warning')} This will restart the bot process.\n"
            f"The bot will be unavailable for ~5 seconds.\n"
            f"{divider()}"
            f"Confirm?"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=sc_confirm_reboot_keyboard())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=sc_confirm_reboot_keyboard())
    except Exception as ex:
        logger.error(f"cb_sc_reboot: {ex}", exc_info=True)


@router.callback_query(F.data == "sc_confirm_reboot")
async def cb_sc_confirm_reboot(callback: CallbackQuery, bot: Bot):
    try:
        if not is_master(callback.from_user.id):
            return
        await callback.answer("Rebooting…", show_alert=False)
        await bot.send_message(
            callback.from_user.id,
            f"{e('reboot')} <b>Rebooting now…</b>\n"
            f"{e('tip')} I'll notify you when I'm back online.",
            parse_mode="HTML",
        )
        # Graceful restart using os.execv
        asyncio.get_event_loop().call_later(1.5, _do_reboot)
    except Exception as ex:
        logger.error(f"cb_sc_confirm_reboot: {ex}", exc_info=True)


def _do_reboot():
    """Restart the current process in-place."""
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as ex:
        logger.critical(f"Reboot failed: {ex}")


# ─── Change Bot Token ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "sc_change_token")
async def cb_sc_change_token(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
        if not is_master(callback.from_user.id):
            return
        await state.set_state(AdminStates.sc_new_token)
        await callback.message.answer(
            f"{e('token')} <b>Change Bot Token</b>\n{divider()}"
            f"{e('warning')} Send your <b>new bot token</b> from @BotFather.\n"
            f"The token will be saved and the bot will restart.\n"
            f"{divider()}"
            f"{e('tip')} Format: <code>1234567890:AABBccDD...</code>",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_super_control"),
        )
    except Exception as ex:
        logger.error(f"cb_sc_change_token: {ex}", exc_info=True)


@router.message(AdminStates.sc_new_token)
async def handle_new_token(message: Message, state: FSMContext, bot: Bot):
    try:
        if not is_master(message.from_user.id):
            return
        new_token = message.text.strip()
        # Basic validation: should contain a colon and be long enough
        if ":" not in new_token or len(new_token) < 30:
            await message.answer(
                f"{e('error')} That doesn't look like a valid bot token.\n"
                f"Format: <code>1234567890:AABBccDD...</code>",
                parse_mode="HTML",
            )
            return

        # Write to config.py
        _update_config_token(new_token)
        await state.clear()

        await message.answer(
            f"{e('success')} <b>Token saved!</b>\n{divider()}"
            f"{e('reboot')} Rebooting now to apply the new token…",
            parse_mode="HTML",
        )
        asyncio.get_event_loop().call_later(2.0, _do_reboot)
    except Exception as ex:
        logger.error(f"handle_new_token: {ex}", exc_info=True)
        await state.clear()
        await message.answer(
            f"{e('error')} Failed to update token: <code>{ex}</code>",
            parse_mode="HTML",
        )


def _update_config_token(new_token: str):
    """Patch BOT_TOKEN in config.py on disk."""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.py")
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    import re
    new_content = re.sub(
        r'(BOT_TOKEN\s*:\s*str\s*=\s*)["\'].*?["\']',
        f'\\g<1>"{new_token}"',
        content,
    )
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(new_content)


# ─── Check Latest Push (GitHub) ───────────────────────────────────────────────

@router.callback_query(F.data == "sc_latest_push")
async def cb_sc_latest_push(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
        if not is_master(callback.from_user.id):
            return

        # Check if we're in a git repo
        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, timeout=10,
        )
        latest_commits = result.stdout.strip() if result.returncode == 0 else "Not a git repo"

        await state.set_state(AdminStates.sc_test_token)
        await callback.message.answer(
            f"{e('github')} <b>Check Latest Push</b>\n{divider()}"
            f"<b>Latest commits:</b>\n<pre>{latest_commits}</pre>\n"
            f"{divider()}"
            f"{e('tip')} To safely test before deploying:\n"
            f"1. Send me a <b>test bot token</b> — I'll pull the latest code and run it\n"
            f"2. You test the new version\n"
            f"3. Confirm to switch the main bot to the new code\n\n"
            f"Send your <b>test bot token</b> now:",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_super_control"),
        )
    except Exception as ex:
        logger.error(f"cb_sc_latest_push: {ex}", exc_info=True)


@router.message(AdminStates.sc_test_token)
async def handle_test_token(message: Message, state: FSMContext, bot: Bot):
    try:
        if not is_master(message.from_user.id):
            return
        test_token = message.text.strip()
        if ":" not in test_token or len(test_token) < 30:
            await message.answer(
                f"{e('error')} Invalid token format. Try again.", parse_mode="HTML",
            )
            return

        await state.update_data(test_token=test_token)
        wait_msg = await message.answer(
            f"{e('loading')} <b>Pulling latest code from GitHub…</b>", parse_mode="HTML",
        )

        # Pull latest
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pull_result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=repo_dir, capture_output=True, text=True, timeout=30,
        )

        pull_output = pull_result.stdout.strip() + "\n" + pull_result.stderr.strip()
        pull_ok = pull_result.returncode == 0

        try:
            await wait_msg.delete()
        except Exception:
            pass

        if not pull_ok:
            await state.clear()
            await message.answer(
                f"{e('error')} <b>Git pull failed!</b>\n"
                f"<pre>{pull_output[:500]}</pre>",
                parse_mode="HTML",
                reply_markup=back_keyboard("admin_super_control"),
            )
            return

        # Start test bot process
        env = os.environ.copy()
        env["BOT_TOKEN"] = test_token
        test_proc = subprocess.Popen(
            [sys.executable, os.path.join(repo_dir, "main.py")],
            env=env, cwd=repo_dir,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        await state.update_data(test_pid=test_proc.pid)
        await state.set_state(AdminStates.sc_confirm_push_state)

        await message.answer(
            f"{e('success')} <b>Test bot started!</b> (PID {test_proc.pid})\n{divider()}"
            f"<b>Git pull output:</b>\n<pre>{pull_output[:300]}</pre>\n{divider()}"
            f"{e('tip')} Test the bot now: @{(await bot.get_me()).username}\n"
            f"When satisfied, tap <b>Confirm Push</b> to restart the main bot with the new code.",
            parse_mode="HTML",
            reply_markup=sc_push_confirm_keyboard(),
        )
    except Exception as ex:
        logger.error(f"handle_test_token: {ex}", exc_info=True)
        await state.clear()
        await message.answer(
            f"{e('error')} Error: <code>{ex}</code>", parse_mode="HTML",
        )


@router.callback_query(F.data == "sc_confirm_push")
async def cb_sc_confirm_push(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        if not is_master(callback.from_user.id):
            return
        await callback.answer("Applying push…")
        data     = await state.get_data()
        test_pid = data.get("test_pid")

        # Kill test bot process if running
        if test_pid:
            try:
                import signal
                os.kill(test_pid, signal.SIGTERM)
            except Exception:
                pass

        await state.clear()
        await bot.send_message(
            callback.from_user.id,
            f"{e('success')} <b>Push confirmed! Rebooting main bot…</b>",
            parse_mode="HTML",
        )
        asyncio.get_event_loop().call_later(1.5, _do_reboot)
    except Exception as ex:
        logger.error(f"cb_sc_confirm_push: {ex}", exc_info=True)


# ═══════════════════════════════════════
# BROADCAST
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        await state.set_state(AdminStates.broadcast_msg)
        await callback.message.answer(
            f"{e('broadcast')} <b>Broadcast</b>\n{divider()}"
            f"Send your broadcast message (text, photo, video, or document).",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_back"),
        )
    except Exception as ex:
        logger.error(f"cb_admin_broadcast: {ex}", exc_info=True)


@router.message(AdminStates.broadcast_msg)
async def handle_broadcast_msg(message: Message, state: FSMContext, bot: Bot):
    try:
        from config import BROADCAST_DELAY
        await state.clear()
        users      = await db.get_all_users()
        sent_count = fail_count = 0

        progress_msg = await message.answer(
            f"{e('loading')} Broadcasting to <b>{len(users)}</b> users…",
            parse_mode="HTML",
        )

        for user in users:
            try:
                await bot.copy_message(
                    chat_id=user["telegram_id"],
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
                sent_count += 1
            except Exception:
                fail_count += 1
            await asyncio.sleep(BROADCAST_DELAY)

        try:
            await progress_msg.delete()
        except Exception:
            pass

        await message.answer(
            f"{e('success')} <b>Broadcast complete!</b>\n{divider()}"
            f"{e('check')} Sent: <b>{sent_count}</b>\n"
            f"{e('error')} Failed: <b>{fail_count}</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_back"),
        )
    except Exception as ex:
        logger.error(f"handle_broadcast_msg: {ex}", exc_info=True)


# ═══════════════════════════════════════
# GIFT CODES MANAGEMENT
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_codes")
async def cb_admin_codes(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.clear()           # clear any stale create/delete code FSM state
        if not await check_admin(callback.from_user.id):
            return
        codes = await db.get_all_gift_codes()
        from keyboards import admin_gift_codes_keyboard

        lines = [f"{e('gift')} <b>GIFT CODES</b>\n{divider()}"]
        for c in codes[:10]:
            lines.append(
                f"{e('star')} <code>{c['code']}</code> — "
                f"<b>{c['points']} pts</b>  "
                f"({c['used_count']}/{c['max_uses']} uses)"
            )
        if not codes:
            lines.append("<i>No codes yet.</i>")

        text = "\n".join(lines)
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_gift_codes_keyboard())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=admin_gift_codes_keyboard())
    except Exception as ex:
        logger.error(f"cb_admin_codes: {ex}", exc_info=True)


@router.callback_query(F.data == "admin_create_code")
async def cb_create_code(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.create_code_name)
        await callback.message.answer(
            f"{e('gift')} <b>Create Gift Code</b>\n{divider()}"
            f"Enter a code name / string:",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_codes"),
        )
    except Exception as ex:
        logger.error(f"cb_create_code: {ex}", exc_info=True)


@router.message(AdminStates.create_code_name)
async def handle_code_name(message: Message, state: FSMContext):
    await state.update_data(code_name=message.text.strip().upper())
    await state.set_state(AdminStates.create_code_points)
    await message.answer(
        f"{e('points')} How many points does this code give?",
        parse_mode="HTML",
    )


@router.message(AdminStates.create_code_points)
async def handle_code_points(message: Message, state: FSMContext):
    try:
        pts = float(message.text.strip())
    except ValueError:
        await message.answer(f"{e('error')} Enter a number.", parse_mode="HTML")
        return
    await state.update_data(code_points=pts)
    await state.set_state(AdminStates.create_code_uses)
    await message.answer(
        f"{e('star')} How many times can it be used? (enter 0 for unlimited)",
        parse_mode="HTML",
    )


@router.message(AdminStates.create_code_uses)
async def handle_code_uses(message: Message, state: FSMContext):
    try:
        uses = int(message.text.strip())
        if uses == 0:
            uses = 999999
    except ValueError:
        await message.answer(f"{e('error')} Enter a number.", parse_mode="HTML")
        return
    await state.update_data(code_uses=uses)
    await state.set_state(AdminStates.create_code_expiry)
    await message.answer(
        f"{e('pending')} Enter expiry date (YYYY-MM-DD) or 0 for no expiry:",
        parse_mode="HTML",
    )


@router.message(AdminStates.create_code_expiry)
async def handle_code_expiry(message: Message, state: FSMContext):
    try:
        data    = await state.get_data()
        expires = None
        txt     = message.text.strip()
        if txt != "0":
            try:
                expires = datetime.strptime(txt, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                await message.answer(
                    f"{e('error')} Invalid date. Use YYYY-MM-DD format.", parse_mode="HTML",
                )
                return

        await db.create_gift_code(
            code=data["code_name"],
            name=data["code_name"],
            points=data["code_points"],
            max_uses=data["code_uses"],
            expires_at=expires,
        )
        await db.log_admin_action(
            f"create_code:{data['code_name']}:{data['code_points']}pts", message.from_user.id,
        )
        await state.clear()
        await message.answer(
            f"{e('success')} Code <code>{data['code_name']}</code> created!\n"
            f"Points: <b>{data['code_points']}</b>  Uses: <b>{data['code_uses']}</b>",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_codes"),
        )
    except Exception as ex:
        logger.error(f"handle_code_expiry: {ex}", exc_info=True)
        await state.clear()
        await message.answer(f"{e('error')} Failed: <code>{ex}</code>", parse_mode="HTML")


@router.callback_query(F.data == "admin_delete_code")
async def cb_delete_code(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.delete_code)
        await callback.message.answer(
            f"{e('remove')} Enter the code to delete:",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_codes"),
        )
    except Exception as ex:
        logger.error(f"cb_delete_code: {ex}", exc_info=True)


@router.message(AdminStates.delete_code)
async def handle_delete_code(message: Message, state: FSMContext):
    try:
        code = message.text.strip().upper()
        await db.delete_gift_code(code)
        await state.clear()
        await message.answer(
            f"{e('success')} Code <code>{code}</code> deleted.",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_codes"),
        )
    except Exception as ex:
        logger.error(f"handle_delete_code: {ex}", exc_info=True)
        await state.clear()


# ═══════════════════════════════════════
# USER MANAGEMENT
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        from keyboards import admin_users_keyboard
        total = await db.get_user_count()
        await callback.message.answer(
            f"{e('admins')} <b>USER MANAGEMENT</b>\n{divider()}"
            f"{e('user')} Total users: <b>{total}</b>\n{divider()}",
            parse_mode="HTML",
            reply_markup=admin_users_keyboard(),
        )
    except Exception as ex:
        logger.error(f"cb_admin_users: {ex}", exc_info=True)


@router.callback_query(F.data == "admin_ban_user")
async def cb_ban_user(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.ban_user)
        await callback.message.answer(
            f"{e('ban')} Enter the username or ID to ban:",
            parse_mode="HTML", reply_markup=back_keyboard("admin_users"),
        )
    except Exception as ex:
        logger.error(f"cb_ban_user: {ex}", exc_info=True)


@router.message(AdminStates.ban_user)
async def handle_ban_user(message: Message, state: FSMContext):
    try:
        ref = message.text.strip()
        user = (
            await db.get_user_by_username(ref.lstrip("@"))
            if not ref.lstrip("-").isdigit()
            else await db.get_user(int(ref))
        )
        if not user:
            await message.answer(f"{e('error')} User not found.", parse_mode="HTML")
            return
        if user["telegram_id"] == MASTER_ADMIN_ID:
            await message.answer(f"{e('error')} Cannot ban the master admin.", parse_mode="HTML")
            return
        await db.set_user_banned(user["telegram_id"], 1)
        await db.log_admin_action(f"ban:{user['telegram_id']}", message.from_user.id)
        await state.clear()
        await message.answer(
            f"{e('ban')} <b>User banned:</b> {user['full_name']}",
            parse_mode="HTML", reply_markup=back_keyboard("admin_users"),
        )
    except Exception as ex:
        logger.error(f"handle_ban_user: {ex}", exc_info=True)
        await state.clear()


@router.callback_query(F.data == "admin_unban_user")
async def cb_unban_user(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.unban_user)
        await callback.message.answer(
            f"{e('success')} Enter the username or ID to unban:",
            parse_mode="HTML", reply_markup=back_keyboard("admin_users"),
        )
    except Exception as ex:
        logger.error(f"cb_unban_user: {ex}", exc_info=True)


@router.message(AdminStates.unban_user)
async def handle_unban_user(message: Message, state: FSMContext):
    try:
        ref = message.text.strip()
        user = (
            await db.get_user_by_username(ref.lstrip("@"))
            if not ref.lstrip("-").isdigit()
            else await db.get_user(int(ref))
        )
        if not user:
            await message.answer(f"{e('error')} User not found.", parse_mode="HTML")
            return
        await db.set_user_banned(user["telegram_id"], 0)
        await db.log_admin_action(f"unban:{user['telegram_id']}", message.from_user.id)
        await state.clear()
        await message.answer(
            f"{e('success')} <b>User unbanned:</b> {user['full_name']}",
            parse_mode="HTML", reply_markup=back_keyboard("admin_users"),
        )
    except Exception as ex:
        logger.error(f"handle_unban_user: {ex}", exc_info=True)
        await state.clear()


@router.callback_query(F.data == "admin_bonus_user")
async def cb_bonus_user(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.give_bonus_user)
        await callback.message.answer(
            f"{e('bonus')} Enter the username or ID to give bonus:",
            parse_mode="HTML", reply_markup=back_keyboard("admin_users"),
        )
    except Exception as ex:
        logger.error(f"cb_bonus_user: {ex}", exc_info=True)


@router.message(AdminStates.give_bonus_user)
async def handle_bonus_user_id(message: Message, state: FSMContext):
    try:
        ref = message.text.strip()
        user = (
            await db.get_user_by_username(ref.lstrip("@"))
            if not ref.lstrip("-").isdigit()
            else await db.get_user(int(ref))
        )
        if not user:
            await message.answer(f"{e('error')} User not found.", parse_mode="HTML")
            return
        await state.update_data(target_user_id=user["telegram_id"], target_name=user["full_name"])
        await state.set_state(AdminStates.give_bonus_amount)
        await message.answer(
            f"{e('points')} How many points to give <b>{user['full_name']}</b>?",
            parse_mode="HTML",
        )
    except Exception as ex:
        logger.error(f"handle_bonus_user_id: {ex}", exc_info=True)
        await state.clear()


@router.message(AdminStates.give_bonus_amount)
async def handle_bonus_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        data = await state.get_data()
        try:
            pts = float(message.text.strip())
        except ValueError:
            await message.answer(f"{e('error')} Enter a number.", parse_mode="HTML")
            return
        uid  = data["target_user_id"]
        name = data["target_name"]
        await db.add_points(uid, pts)
        await db.log_admin_action(f"bonus:{uid}:{pts}", message.from_user.id)
        await state.clear()
        try:
            await bot.send_message(
                uid,
                f"{e('bonus')} <b>Bonus received!</b>\n"
                f"{e('points')} <b>+{pts} pts</b> from admin.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await message.answer(
            f"{e('success')} Gave <b>{pts} pts</b> to <b>{name}</b>.",
            parse_mode="HTML", reply_markup=back_keyboard("admin_users"),
        )
    except Exception as ex:
        logger.error(f"handle_bonus_amount: {ex}", exc_info=True)
        await state.clear()


@router.callback_query(F.data == "admin_bonus_all")
async def cb_bonus_all(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.give_bonus_all)
        await callback.message.answer(
            f"{e('sparkle')} How many points to give ALL users?",
            parse_mode="HTML", reply_markup=back_keyboard("admin_users"),
        )
    except Exception as ex:
        logger.error(f"cb_bonus_all: {ex}", exc_info=True)


@router.message(AdminStates.give_bonus_all)
async def handle_bonus_all(message: Message, state: FSMContext, bot: Bot):
    try:
        from config import BROADCAST_DELAY
        try:
            pts = float(message.text.strip())
        except ValueError:
            await message.answer(f"{e('error')} Enter a number.", parse_mode="HTML")
            return
        await state.clear()
        users = await db.get_all_users()
        for user in users:
            await db.add_points(user["telegram_id"], pts)
        await db.log_admin_action(f"bonus_all:{pts}:{len(users)}", message.from_user.id)
        await message.answer(
            f"{e('success')} Gave <b>{pts} pts</b> to <b>{len(users)}</b> users.",
            parse_mode="HTML", reply_markup=back_keyboard("admin_users"),
        )
    except Exception as ex:
        logger.error(f"handle_bonus_all: {ex}", exc_info=True)
        await state.clear()


# ═══════════════════════════════════════
# ADMINS MANAGEMENT
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_admins")
async def cb_admin_admins(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        admins = await db.get_all_admins()
        lines  = [f"{e('admins')} <b>BOT ADMINS</b>\n{divider()}"]
        for adm in admins:
            icon = e("crown") if adm["user_id"] == MASTER_ADMIN_ID else e("key")
            tag  = "<b>Master</b>" if adm["user_id"] == MASTER_ADMIN_ID else adm.get("role","admin")
            uname = f"@{adm['username']}" if adm.get("username") else str(adm["user_id"])
            lines.append(f"{icon} <code>{uname}</code> — {tag}")
        text = "\n".join(lines)
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=admin_admins_keyboard(admins, MASTER_ADMIN_ID))
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=admin_admins_keyboard(admins, MASTER_ADMIN_ID))
    except Exception as ex:
        logger.error(f"cb_admin_admins: {ex}", exc_info=True)


@router.callback_query(F.data == "admin_add_admin")
async def cb_add_admin(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        await state.set_state(AdminStates.add_admin)
        await callback.message.answer(
            f"{e('plus')} Enter the username or ID of the new admin:",
            parse_mode="HTML", reply_markup=back_keyboard("admin_admins"),
        )
    except Exception as ex:
        logger.error(f"cb_add_admin: {ex}", exc_info=True)


@router.message(AdminStates.add_admin)
async def handle_add_admin(message: Message, state: FSMContext):
    try:
        ref = message.text.strip()
        user = (
            await db.get_user_by_username(ref.lstrip("@"))
            if not ref.lstrip("-").isdigit()
            else await db.get_user(int(ref))
        )
        if not user:
            await message.answer(f"{e('error')} User not found in DB.", parse_mode="HTML")
            return
        await db.add_admin(user["telegram_id"], user.get("username",""), "admin")
        await db.log_admin_action(f"add_admin:{user['telegram_id']}", message.from_user.id)
        await state.clear()
        await message.answer(
            f"{e('success')} <b>{user['full_name']}</b> is now an admin.",
            parse_mode="HTML", reply_markup=back_keyboard("admin_admins"),
        )
    except Exception as ex:
        logger.error(f"handle_add_admin: {ex}", exc_info=True)
        await state.clear()


@router.callback_query(F.data == "admin_remove_admin")
async def cb_remove_admin(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        await state.set_state(AdminStates.remove_admin)
        await callback.message.answer(
            f"{e('remove')} Enter the username or ID to remove from admins:",
            parse_mode="HTML", reply_markup=back_keyboard("admin_admins"),
        )
    except Exception as ex:
        logger.error(f"cb_remove_admin: {ex}", exc_info=True)


@router.message(AdminStates.remove_admin)
async def handle_remove_admin(message: Message, state: FSMContext):
    try:
        ref = message.text.strip()
        user = (
            await db.get_user_by_username(ref.lstrip("@"))
            if not ref.lstrip("-").isdigit()
            else await db.get_user(int(ref))
        )
        if not user:
            await message.answer(f"{e('error')} User not found.", parse_mode="HTML")
            return
        if user["telegram_id"] == MASTER_ADMIN_ID:
            await message.answer(f"{e('error')} Cannot remove the master admin.", parse_mode="HTML")
            return
        await db.remove_admin(user["telegram_id"])
        await db.log_admin_action(f"remove_admin:{user['telegram_id']}", message.from_user.id)
        await state.clear()
        await message.answer(
            f"{e('success')} <b>{user['full_name']}</b> removed from admins.",
            parse_mode="HTML", reply_markup=back_keyboard("admin_admins"),
        )
    except Exception as ex:
        logger.error(f"handle_remove_admin: {ex}", exc_info=True)
        await state.clear()


# ═══════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_settings")
async def cb_admin_settings(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        s = await db.get_all_settings()
        cap  = s.get("captcha_enabled","0")
        rev  = s.get("force_reverify","0")
        text = (
            f"{e('settings')} <b>BOT SETTINGS</b>\n{divider()}"
            f"{e('withdraw')} Min Withdraw: <b>{s.get('min_withdraw_points','10')} pts</b>\n"
            f"{e('refer')} Pts/Refer: <b>{s.get('points_per_refer','5')}</b>\n"
            f"{e('followers')} Followers: <b>{s.get('followers_points','10')} pts = {s.get('followers_amount','100')}</b>\n"
            f"{e('likes')} Likes: <b>{s.get('likes_points','5')} pts = {s.get('likes_amount','50')}</b>\n"
            f"{e('views')} Views: <b>{s.get('views_points','3')} pts = {s.get('views_amount','100')}</b>\n"
            f"{e('comments')} Comments: <b>{s.get('comments_points','15')} pts = {s.get('comments_amount','10')}</b>\n"
            f"{e('captcha')} Captcha: <b>{'ON ✅' if cap=='1' else 'OFF ❌'}</b>\n"
            f"{e('refresh')} Force Reverify: <b>{'ON ✅' if rev=='1' else 'OFF ❌'}</b>\n"
            f"{divider()}"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=admin_settings_keyboard())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=admin_settings_keyboard())
    except Exception as ex:
        logger.error(f"cb_admin_settings: {ex}", exc_info=True)


async def _save_numeric_setting(
    message: Message, state: FSMContext,
    key: str, label: str,
):
    try:
        val = message.text.strip()
        try:
            float(val)
        except ValueError:
            await message.answer(f"{e('error')} Enter a valid number.", parse_mode="HTML")
            return
        await db.set_setting(key, val)
        await db.log_admin_action(f"set_{key}:{val}", message.from_user.id)
        await state.clear()
        await message.answer(
            f"{e('success')} <b>{label}</b> set to <code>{val}</code>",
            parse_mode="HTML", reply_markup=back_keyboard("admin_settings"),
        )
    except Exception as ex:
        logger.error(f"_save_numeric_setting: {ex}", exc_info=True)


async def _ask_setting(callback: CallbackQuery, state: FSMContext, prompt: str, fsm_state):
    await callback.answer()
    await state.set_state(fsm_state)
    await callback.message.answer(prompt, parse_mode="HTML",
                                  reply_markup=back_keyboard("admin_settings"))


@router.callback_query(F.data == "setting_min_withdraw")
async def cb_min_withdraw(callback: CallbackQuery, state: FSMContext):
    await _ask_setting(callback, state, f"{e('withdraw')} Enter new minimum withdraw points:", AdminStates.set_min_points)


@router.message(AdminStates.set_min_points)
async def handle_min_points(message: Message, state: FSMContext):
    await _save_numeric_setting(message, state, "min_withdraw_points", "Minimum Withdraw Points")


@router.callback_query(F.data == "setting_points_per_refer")
async def cb_ppr(callback: CallbackQuery, state: FSMContext):
    await _ask_setting(callback, state, f"{e('refer')} Enter new points per refer:", AdminStates.set_refer_points)


@router.message(AdminStates.set_refer_points)
async def handle_refer_points(message: Message, state: FSMContext):
    await _save_numeric_setting(message, state, "points_per_refer", "Points Per Refer")


async def _ask_ratio(callback: CallbackQuery, state: FSMContext, svc: str, fsm_state):
    await callback.answer()
    await state.set_state(fsm_state)
    await state.update_data(ratio_service=svc)
    pts = await db.get_setting(f"{svc}_points", "5")
    amt = await db.get_setting(f"{svc}_amount", "50")
    await callback.message.answer(
        f"{e('settings')} <b>{svc.capitalize()} Ratio</b>\n"
        f"Current: <code>{pts} pts = {amt}</code>\n\n"
        f"Enter new ratio as: <code>POINTS:AMOUNT</code>",
        parse_mode="HTML",
        reply_markup=back_keyboard("admin_settings"),
    )


async def _save_ratio(message: Message, state: FSMContext):
    try:
        data    = await state.get_data()
        service = data["ratio_service"]
        parts   = message.text.strip().split(":")
        if len(parts) != 2:
            await message.answer(f"{e('error')} Format: <code>POINTS:AMOUNT</code>", parse_mode="HTML")
            return
        pts, amt = parts
        await db.set_setting(f"{service}_points", pts.strip())
        await db.set_setting(f"{service}_amount", amt.strip())
        await db.log_admin_action(f"set_ratio:{service}={pts}:{amt}", message.from_user.id)
        await state.clear()
        await message.answer(
            f"{e('success')} <b>{service.capitalize()} ratio:</b> "
            f"<code>{pts.strip()}</code> pts = <code>{amt.strip()}</code>",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_settings"),
        )
    except Exception as ex:
        logger.error(f"_save_ratio: {ex}", exc_info=True)


@router.callback_query(F.data == "setting_followers_ratio")
async def cb_followers_ratio(callback: CallbackQuery, state: FSMContext):
    await _ask_ratio(callback, state, "followers", AdminStates.set_followers_ratio)

@router.message(AdminStates.set_followers_ratio)
async def handle_followers_ratio(message: Message, state: FSMContext):
    await _save_ratio(message, state)


@router.callback_query(F.data == "setting_likes_ratio")
async def cb_likes_ratio(callback: CallbackQuery, state: FSMContext):
    await _ask_ratio(callback, state, "likes", AdminStates.set_likes_ratio)

@router.message(AdminStates.set_likes_ratio)
async def handle_likes_ratio(message: Message, state: FSMContext):
    await _save_ratio(message, state)


@router.callback_query(F.data == "setting_views_ratio")
async def cb_views_ratio(callback: CallbackQuery, state: FSMContext):
    await _ask_ratio(callback, state, "views", AdminStates.set_views_ratio)

@router.message(AdminStates.set_views_ratio)
async def handle_views_ratio(message: Message, state: FSMContext):
    await _save_ratio(message, state)


@router.callback_query(F.data == "setting_comments_ratio")
async def cb_comments_ratio(callback: CallbackQuery, state: FSMContext):
    await _ask_ratio(callback, state, "comments", AdminStates.set_comments_ratio)

@router.message(AdminStates.set_comments_ratio)
async def handle_comments_ratio(message: Message, state: FSMContext):
    await _save_ratio(message, state)


@router.callback_query(F.data == "setting_toggle_captcha")
async def cb_toggle_captcha(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        cur = await db.get_setting("captcha_enabled", "0")
        new = "0" if cur == "1" else "1"
        await db.set_setting("captcha_enabled", new)
        status = f"ENABLED {e('check')}" if new == "1" else f"DISABLED {e('error')}"
        await callback.message.answer(
            f"{e('captcha')} Captcha is now <b>{status}</b>",
            parse_mode="HTML", reply_markup=admin_captcha_keyboard(new == "1"),
        )
    except Exception as ex:
        logger.error(f"cb_toggle_captcha: {ex}", exc_info=True)


@router.callback_query(F.data == "setting_toggle_reverify")
async def cb_toggle_reverify(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        cur = await db.get_setting("force_reverify", "0")
        new = "0" if cur == "1" else "1"
        await db.set_setting("force_reverify", new)
        # If turning ON, reset all users' verified status
        if new == "1":
            await db.col("users").update_many({}, {"$set": {"is_verified": 0}})
        status = f"ENABLED {e('check')}" if new == "1" else f"DISABLED {e('error')}"
        await callback.message.answer(
            f"{e('refresh')} Force Reverify is now <b>{status}</b>",
            parse_mode="HTML", reply_markup=back_keyboard("admin_settings"),
        )
    except Exception as ex:
        logger.error(f"cb_toggle_reverify: {ex}", exc_info=True)


# ═══════════════════════════════════════
# API CONFIG
# ═══════════════════════════════════════

async def _api_config_text() -> tuple[str, bool]:
    api_key = await db.get_setting("jap_api_key", "")
    api_url = await db.get_setting("jap_api_url", "") or JAP_BASE_URL
    has_key = bool(api_key and api_key not in ("TEST_API_KEY_12345", "YOUR_JAP_API_KEY_HERE"))
    if has_key:
        masked = (api_key[:4] + "●" * 8 + api_key[-4:]) if len(api_key) > 8 else "●" * 12
        mode_label = f"{e('live')} <b>LIVE MODE</b>"
    else:
        masked = "<i>Not set</i>"
        mode_label = f"{e('warning')} <b>TEST MODE</b>"
    text = (
        f"{e('key')} <b>API CONFIG</b>\n{divider()}"
        f"{e('panel')} Mode: {mode_label}\n{divider()}"
        f"{e('star')} Key: <code>{masked}</code>\n"
        f"{e('link')} URL: <code>{api_url}</code>\n{divider()}"
    )
    return text, has_key


@router.callback_query(F.data == "admin_api_config")
async def cb_api_config(callback: CallbackQuery, bot: Bot, state: FSMContext):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        await state.clear()
        text, has_key = await _api_config_text()
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=admin_api_config_keyboard(has_key))
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=admin_api_config_keyboard(has_key))
    except Exception as ex:
        logger.error(f"cb_api_config: {ex}", exc_info=True)


@router.callback_query(F.data == "admin_set_api_key")
async def cb_set_api_key(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.set_api_key)
        await callback.message.answer(
            f"{e('key')} Enter your JAP API key:",
            parse_mode="HTML", reply_markup=back_keyboard("admin_api_config"),
        )
    except Exception as ex:
        logger.error(f"cb_set_api_key: {ex}", exc_info=True)


@router.message(AdminStates.set_api_key)
async def handle_set_api_key(message: Message, state: FSMContext):
    try:
        val = message.text.strip()
        await db.set_setting("jap_api_key", val)
        jap.reload(api_key=val)
        await db.log_admin_action("set_api_key", message.from_user.id)
        await state.clear()
        await message.answer(
            f"{e('success')} API key saved and applied live.",
            parse_mode="HTML", reply_markup=back_keyboard("admin_api_config"),
        )
    except Exception as ex:
        logger.error(f"handle_set_api_key: {ex}", exc_info=True)
        await state.clear()


@router.callback_query(F.data == "admin_set_api_url")
async def cb_set_api_url(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.set_api_url)
        await callback.message.answer(
            f"{e('link')} Enter the API base URL:",
            parse_mode="HTML", reply_markup=back_keyboard("admin_api_config"),
        )
    except Exception as ex:
        logger.error(f"cb_set_api_url: {ex}", exc_info=True)


@router.message(AdminStates.set_api_url)
async def handle_set_api_url(message: Message, state: FSMContext):
    try:
        val = message.text.strip()
        await db.set_setting("jap_api_url", val)
        jap.reload(base_url=val)
        await state.clear()
        await message.answer(
            f"{e('success')} API URL saved and applied live.",
            parse_mode="HTML", reply_markup=back_keyboard("admin_api_config"),
        )
    except Exception as ex:
        logger.error(f"handle_set_api_url: {ex}", exc_info=True)
        await state.clear()


@router.callback_query(F.data == "admin_delete_api_key")
async def cb_delete_api_key(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        await db.set_setting("jap_api_key", "")
        jap.reload(api_key="TEST_API_KEY_12345")
        await callback.message.answer(
            f"{e('warning')} API key deleted. Back to <b>TEST MODE</b>.",
            parse_mode="HTML", reply_markup=back_keyboard("admin_api_config"),
        )
    except Exception as ex:
        logger.error(f"cb_delete_api_key: {ex}", exc_info=True)


# ═══════════════════════════════════════
# PROOF CHANNEL
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_proof_channel")
async def cb_admin_proof_channel(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        cid  = await db.get_setting("proof_channel_id", "") or "<i>Not set</i>"
        link = await db.get_setting("proof_channel_link", "") or "<i>Not set</i>"
        text = (
            f"{e('proofs')} <b>PROOF CHANNEL</b>\n{divider()}"
            f"{e('id')} Channel ID: <code>{cid}</code>\n"
            f"{e('link')} Link: <code>{link}</code>\n"
            f"{divider()}"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=admin_proof_channel_keyboard())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=admin_proof_channel_keyboard())
    except Exception as ex:
        logger.error(f"cb_admin_proof_channel: {ex}", exc_info=True)


@router.callback_query(F.data == "admin_set_proof_channel_id")
async def cb_set_proof_channel_id(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.proof_channel_id_input)
        await callback.message.answer(
            f"{e('id')} Enter the numeric proof channel ID:",
            parse_mode="HTML", reply_markup=back_keyboard("admin_proof_channel"),
        )
    except Exception as ex:
        logger.error(f"cb_set_proof_channel_id: {ex}", exc_info=True)


@router.message(AdminStates.proof_channel_id_input)
async def handle_proof_channel_id(message: Message, state: FSMContext):
    try:
        await db.set_setting("proof_channel_id", message.text.strip())
        await state.clear()
        await message.answer(
            f"{e('success')} Proof channel ID saved.",
            parse_mode="HTML", reply_markup=back_keyboard("admin_proof_channel"),
        )
    except Exception as ex:
        logger.error(f"handle_proof_channel_id: {ex}", exc_info=True)
        await state.clear()


@router.callback_query(F.data == "admin_set_proof_channel_link")
async def cb_set_proof_channel_link(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.proof_channel_link_input)
        await callback.message.answer(
            f"{e('link')} Enter the proof channel invite link:",
            parse_mode="HTML", reply_markup=back_keyboard("admin_proof_channel"),
        )
    except Exception as ex:
        logger.error(f"cb_set_proof_channel_link: {ex}", exc_info=True)


@router.message(AdminStates.proof_channel_link_input)
async def handle_proof_channel_link(message: Message, state: FSMContext):
    try:
        await db.set_setting("proof_channel_link", message.text.strip())
        await state.clear()
        await message.answer(
            f"{e('success')} Proof channel link saved.",
            parse_mode="HTML", reply_markup=back_keyboard("admin_proof_channel"),
        )
    except Exception as ex:
        logger.error(f"handle_proof_channel_link: {ex}", exc_info=True)
        await state.clear()


# ═══════════════════════════════════════
# IMAGE MANAGER
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_images")
async def cb_admin_images(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        # Build image status dict for all screens
        images = {}
        for screen in SCREENS:
            images[screen] = await db.get_image(screen)
        try:
            await callback.message.edit_text(
                f"{e('instagram')} <b>IMAGE MANAGER</b>\n{divider()}"
                f"Choose a screen to manage:",
                parse_mode="HTML",
                reply_markup=admin_image_manager_keyboard(SCREENS, images),
            )
        except Exception:
            await callback.message.answer(
                f"{e('instagram')} <b>IMAGE MANAGER</b>\n{divider()}"
                f"Choose a screen to manage:",
                parse_mode="HTML",
                reply_markup=admin_image_manager_keyboard(SCREENS, images),
            )
    except Exception as ex:
        logger.error(f"cb_admin_images: {ex}", exc_info=True)


@router.callback_query(F.data.startswith("imgmgr_"))
async def cb_imgmgr_screen(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        screen  = callback.data.replace("imgmgr_", "")
        file_id = await db.get_image(screen)
        has     = bool(file_id)
        text    = (
            f"{e('instagram')} <b>{screen.capitalize()} Image</b>\n{divider()}"
            f"Status: {e('check') + ' Set' if has else e('error') + ' Not set'}"
        )
        await callback.message.answer(
            text, parse_mode="HTML",
            reply_markup=admin_image_actions_keyboard(screen, has),
        )
    except Exception as ex:
        logger.error(f"cb_imgmgr_screen: {ex}", exc_info=True)


@router.callback_query(F.data.startswith("imgset_"))
async def cb_imgset(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        screen = callback.data.replace("imgset_", "")
        await state.set_state(AdminStates.upload_image_waiting)
        await state.update_data(image_screen=screen)
        await callback.message.answer(
            f"{e('instagram')} Send a photo for the <b>{screen}</b> screen:",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_images"),
        )
    except Exception as ex:
        logger.error(f"cb_imgset: {ex}", exc_info=True)


@router.message(AdminStates.upload_image_waiting)
async def handle_image_upload(message: Message, state: FSMContext):
    try:
        data   = await state.get_data()
        screen = data.get("image_screen", "")
        if not message.photo:
            await message.answer(f"{e('error')} Please send a photo.", parse_mode="HTML")
            return
        file_id = message.photo[-1].file_id
        await db.set_image(screen, file_id)
        await db.log_admin_action(f"set_image:{screen}", message.from_user.id)
        await state.clear()
        await message.answer(
            f"{e('success')} Image set for <b>{screen}</b>.",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_images"),
        )
    except Exception as ex:
        logger.error(f"handle_image_upload: {ex}", exc_info=True)
        await state.clear()


@router.callback_query(F.data.startswith("imgdel_"))
async def cb_imgdel(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        screen = callback.data.replace("imgdel_", "")
        await db.delete_image(screen)
        await db.log_admin_action(f"delete_image:{screen}", callback.from_user.id)
        await callback.message.answer(
            f"{e('success')} Image removed for <b>{screen}</b>.",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_images"),
        )
    except Exception as ex:
        logger.error(f"cb_imgdel: {ex}", exc_info=True)


# ═══════════════════════════════════════
# MESSAGES (promo + menu editor)
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_messages")
async def cb_admin_messages(callback: CallbackQuery, bot: Bot, state: FSMContext):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        await state.clear()
        promo_mode = await db.get_setting("promo_mode", "always")
        has_promo  = bool(await db.get_setting("promo_text", ""))
        has_menu   = bool(await db.get_setting("menu_text", ""))
        text = (
            f"{e('promo')} <b>MESSAGES</b>\n{divider()}"
            f"{e('check') if has_promo else e('error')} Promo: <b>{'Custom' if has_promo else 'Default'}</b>\n"
            f"{e('check') if has_menu  else e('error')} Menu:  <b>{'Custom' if has_menu  else 'Default'}</b>\n"
            f"{e('refresh')} Promo Mode: <b>{promo_mode}</b>\n{divider()}"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=admin_messages_keyboard())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=admin_messages_keyboard())
    except Exception as ex:
        logger.error(f"cb_admin_messages: {ex}", exc_info=True)


@router.callback_query(F.data == "admin_edit_promo")
async def cb_edit_promo(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.edit_promo_msg)
        await callback.message.answer(
            f"{e('promo')} Send your new promo message (supports premium emojis):",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_messages"),
        )
    except Exception as ex:
        logger.error(f"cb_edit_promo: {ex}", exc_info=True)


@router.message(AdminStates.edit_promo_msg)
async def handle_edit_promo_msg(message: Message, state: FSMContext):
    try:
        text     = message.text or message.caption or ""
        entities = message.entities or message.caption_entities or []

        # Serialise ALL entity fields including custom_emoji_id so premium
        # animated emojis round-trip correctly through the DB.
        def _serialise_entity(ent) -> dict:
            d = ent.model_dump(mode="json")
            # Ensure custom_emoji_id is preserved (critical for premium emojis)
            if ent.type == "custom_emoji" and ent.custom_emoji_id:
                d["custom_emoji_id"] = ent.custom_emoji_id
            # Drop null values to keep JSON clean
            return {k: v for k, v in d.items() if v is not None}

        entities_json = json.dumps([_serialise_entity(ent) for ent in entities])

        await db.set_setting("promo_text",     text)
        await db.set_setting("promo_entities", entities_json)
        await db.log_admin_action("set_promo_message", message.from_user.id)
        await state.clear()

        # Preview: count premium emojis saved
        premium_count = sum(1 for ent in entities if ent.type == "custom_emoji")
        extra = f"\n{e('sparkle')} <b>{premium_count}</b> premium emoji(s) saved." if premium_count else ""
        await message.answer(
            f"{e('success')} Promo message updated!{extra}",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_messages"),
        )
    except Exception as ex:
        logger.error(f"handle_edit_promo_msg: {ex}", exc_info=True)
        await state.clear()


@router.callback_query(F.data == "admin_edit_menu")
async def cb_edit_menu(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        await state.set_state(AdminStates.edit_menu_msg)
        await callback.message.answer(
            f"{e('menu')} Send your new main menu message:",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_messages"),
        )
    except Exception as ex:
        logger.error(f"cb_edit_menu: {ex}", exc_info=True)


@router.message(AdminStates.edit_menu_msg)
async def handle_edit_menu_msg(message: Message, state: FSMContext):
    try:
        text     = message.text or message.caption or ""
        entities = message.entities or message.caption_entities or []

        def _serialise_entity(ent) -> dict:
            d = ent.model_dump(mode="json")
            if ent.type == "custom_emoji" and ent.custom_emoji_id:
                d["custom_emoji_id"] = ent.custom_emoji_id
            return {k: v for k, v in d.items() if v is not None}

        entities_json = json.dumps([_serialise_entity(ent) for ent in entities])
        await db.set_setting("menu_text",     text)
        await db.set_setting("menu_entities", entities_json)
        await db.log_admin_action("set_menu_message", message.from_user.id)
        await state.clear()
        premium_count = sum(1 for ent in entities if ent.type == "custom_emoji")
        extra = f"\n{e('sparkle')} <b>{premium_count}</b> premium emoji(s) saved." if premium_count else ""
        await message.answer(
            f"{e('success')} Menu message updated!{extra}",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_messages"),
        )
    except Exception as ex:
        logger.error(f"handle_edit_menu_msg: {ex}", exc_info=True)
        await state.clear()


@router.callback_query(F.data == "admin_toggle_promo_mode")
async def cb_toggle_promo_mode(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        cur = await db.get_setting("promo_mode", "always")
        new = "once" if cur == "always" else "always"
        await db.set_setting("promo_mode", new)
        await callback.message.answer(
            f"{e('refresh')} Promo mode set to <b>{new}</b>.",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_messages"),
        )
    except Exception as ex:
        logger.error(f"cb_toggle_promo_mode: {ex}", exc_info=True)


@router.callback_query(F.data == "admin_reset_promo")
async def cb_reset_promo(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        await callback.message.answer(
            f"{e('warning')} Are you sure you want to reset the promo message to default?",
            parse_mode="HTML",
            reply_markup=admin_messages_confirm_reset_keyboard("promo"),
        )
    except Exception as ex:
        logger.error(f"cb_reset_promo: {ex}", exc_info=True)


@router.callback_query(F.data == "admin_reset_menu")
async def cb_reset_menu(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        await callback.message.answer(
            f"{e('warning')} Are you sure you want to reset the menu message to default?",
            parse_mode="HTML",
            reply_markup=admin_messages_confirm_reset_keyboard("menu"),
        )
    except Exception as ex:
        logger.error(f"cb_reset_menu: {ex}", exc_info=True)


@router.callback_query(F.data.startswith("admin_confirm_reset_"))
async def cb_confirm_reset(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        target = callback.data.replace("admin_confirm_reset_", "")
        if target == "promo":
            await db.set_setting("promo_text",     "")
            await db.set_setting("promo_entities", "")
        elif target == "menu":
            await db.set_setting("menu_text",     "")
            await db.set_setting("menu_entities", "")
        await callback.message.answer(
            f"{e('success')} <b>{target.capitalize()} message</b> reset to default.",
            parse_mode="HTML",
            reply_markup=back_keyboard("admin_messages"),
        )
    except Exception as ex:
        logger.error(f"cb_confirm_reset: {ex}", exc_info=True)


# ═══════════════════════════════════════
# ORDERS VIEW
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_orders")
async def cb_admin_orders(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return
        orders = await db.get_pending_orders()
        text   = (
            f"{e('stock')} <b>PENDING ORDERS</b>\n{divider()}"
            f"Count: <b>{len(orders)}</b>\n{divider()}"
        )
        try:
            await callback.message.edit_text(text, parse_mode="HTML",
                                             reply_markup=admin_pending_orders_keyboard(orders))
        except Exception:
            await callback.message.answer(text, parse_mode="HTML",
                                          reply_markup=admin_pending_orders_keyboard(orders))
    except Exception as ex:
        logger.error(f"cb_admin_orders: {ex}", exc_info=True)


# ═══════════════════════════════════════
# INDIVIDUAL ORDER DETAIL  (tap an order row in the pending list)
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("admin_order_"))
async def cb_admin_order_detail(callback: CallbackQuery, bot: Bot):
    try:
        await callback.answer()
        if not await check_admin(callback.from_user.id):
            return

        order_id = callback.data.replace("admin_order_", "")
        order    = await db.get_order(order_id)
        if not order:
            await callback.message.answer(
                f"{e('error')} Order not found.", parse_mode="HTML",
                reply_markup=back_keyboard("admin_orders"),
            )
            return

        # Fetch live status from JAP
        jap_id      = order.get("jap_order_id", "")
        live_status = None
        remains     = "?"
        if jap_id:
            try:
                status_info = await jap.check_status(jap_id)
                if status_info:
                    live_status = status_info.get("status")
                    remains     = status_info.get("remains", "?")
                    await db.update_order_status(order_id, live_status)
            except Exception as ex:
                logger.warning(f"cb_admin_order_detail check_status: {ex}")

        status = live_status or order.get("status", "unknown")
        SEV = {
            "Completed":   e("success"), "completed":   e("success"),
            "In progress": e("loading"), "processing":  e("loading"),
            "pending":     e("pending"),
            "Partial":     e("warning"),
            "Cancelled":   e("error"),   "Failed": e("error"),
            "cancelled":   e("error"),   "failed": e("error"),
        }
        sev = SEV.get(status, e("loading"))

        pts_spent = order.get("points_spent", 0)
        created   = order.get("created_at")
        created_s = created.strftime("%Y-%m-%d %H:%M UTC") if hasattr(created, "strftime") else str(created)

        user = await db.get_user(order["user_id"])
        user_str = (
            f"{user['full_name']} (@{user['username']})" if user else f"ID {order['user_id']}"
        )

        text = (
            f"{e('botstats')} <b>Order Detail</b>\n{divider()}"
            f"{e('user')} {user_str}\n"
            f"{e('key')} JAP ID: <code>#{jap_id}</code>\n"
            f"{e('instagram')} Service: <b>{order['service'].capitalize()}</b>\n"
            f"{e('followers')} Quantity: <b>{order['quantity']}</b>\n"
            f"{e('link')} <code>{order.get('instagram_link','')}</code>\n"
            f"{e('points')} Points: <b>{pts_spent}</b>\n"
            f"{divider()}"
            f"{sev} Status: <b>{status}</b>  |  Remains: <code>{remains}</code>\n"
            f"{e('tip')} Created: <code>{created_s}</code>\n"
        )
        if order.get("refunded"):
            text += f"{e('bonus')} Refunded: <b>Yes</b>\n"

        try:
            await callback.message.edit_text(
                text, parse_mode="HTML",
                reply_markup=admin_order_detail_keyboard(order_id),
            )
        except Exception:
            await callback.message.answer(
                text, parse_mode="HTML",
                reply_markup=admin_order_detail_keyboard(order_id),
            )
    except Exception as ex:
        logger.error(f"cb_admin_order_detail: {ex}", exc_info=True)


# ═══════════════════════════════════════
# LEGACY / COMPATIBILITY CALLBACKS
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_custom_messages")
async def cb_legacy_messages(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await cb_admin_messages(callback, bot, state)
