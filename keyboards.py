"""
keyboards.py — All keyboards for the bot.
Rules:
  • style= values: only 'primary' (blue), 'success' (green), 'danger' (red)
  • icon_custom_emoji_id on both KeyboardButton (reply) and InlineKeyboardButton (inline)
    — guarded by PREMIUM_EMOJI_ENABLED via _eid(); None is silently ignored
  • Emoji fallback chars embedded in button text via _fb() for non-premium clients
"""

from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from emojis import PREMIUM
from config import DEVELOPER_USERNAME, GENERAL_SUPPORT_USERNAME, PREMIUM_EMOJI_ENABLED


def _fb(name: str) -> str:
    """Return the fallback emoji character for a given key."""
    val = PREMIUM.get(name, ("", ""))
    if isinstance(val, tuple) and len(val) >= 2:
        return val[1]
    return ""


def _eid(name: str) -> str | None:
    """Return the Telegram custom emoji ID string for a given key, or None when
    PREMIUM_EMOJI_ENABLED is False (so icon_custom_emoji_id is silently omitted
    and buttons still render without errors on non-Premium bot owners)."""
    if not PREMIUM_EMOJI_ENABLED:
        return None
    val = PREMIUM.get(name, ("", ""))
    if isinstance(val, tuple) and len(val) >= 1 and val[0]:
        return val[0]
    return None


# ═══════════════════════════════════════
# BUTTON TEXT CONSTANTS  (use these for exact-match filters in handlers)
# ═══════════════════════════════════════

BTN_BALANCE   = f"{_fb('balance_menu')} Balance"
BTN_REFER     = f"{_fb('refer_menu')} Refer"
BTN_STOCK     = f"{_fb('botstats')} Stock"
BTN_SUPPORT   = f"{_fb('support')} Support"
BTN_PROOFS    = f"{_fb('proofs')} Proofs"
BTN_GIFT      = f"{_fb('gift')} Gift Code"
BTN_WITHDRAW  = f"{_fb('withdraw')} Withdraw"
BTN_MAIN_MENU = f"{_fb('menu')} Main Menu"


# ═══════════════════════════════════════
# REPLY KEYBOARD  (main menu)
# ═══════════════════════════════════════

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(
        KeyboardButton(text=BTN_BALANCE,   style="success", icon_custom_emoji_id=_eid('balance_menu')),
        KeyboardButton(text=BTN_REFER,     style="primary", icon_custom_emoji_id=_eid('refer_menu')),
    )
    b.row(
        KeyboardButton(text=BTN_STOCK,     style="primary", icon_custom_emoji_id=_eid('botstats')),
        KeyboardButton(text=BTN_SUPPORT,   style="success", icon_custom_emoji_id=_eid('support')),
    )
    b.row(
        KeyboardButton(text=BTN_PROOFS,    style="primary", icon_custom_emoji_id=_eid('proofs')),
        KeyboardButton(text=BTN_GIFT,      style="success", icon_custom_emoji_id=_eid('gift')),
    )
    b.row(
        KeyboardButton(text=BTN_WITHDRAW,  style="danger",  icon_custom_emoji_id=_eid('withdraw')),
        KeyboardButton(text=BTN_MAIN_MENU, style="primary", icon_custom_emoji_id=_eid('menu')),
    )
    return b.as_markup(resize_keyboard=True, persistent=True)


# ═══════════════════════════════════════
# PROMO / FORCE-JOIN KEYBOARDS
# ═══════════════════════════════════════

def continue_button() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('fire')} Continue", callback_data="continue_promo",
             style="success", icon_custom_emoji_id=_eid('fire'))
    return b.as_markup()


def force_join_keyboard(channels: list, joined: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    STYLES = ["primary", "success", "danger", "primary"]
    for idx, ch in enumerate(channels):
        display = ch.get("display_name") or ""
        if not display:
            uname = ch.get("channel_username", "")
            display = f"@{uname.lstrip('@')}" if uname else "Channel"
        link = ch.get("channel_link") or ""
        if not link:
            uname = ch.get("channel_username", "")
            link = f"https://t.me/{uname.lstrip('@')}" if uname else ""
        b.button(
            text=f"{_fb('channel')} Join {display}",
            url=link,
            style=STYLES[idx % len(STYLES)],
            icon_custom_emoji_id=_eid('channel'),
        )
    b.adjust(1)
    b.button(text=f"{_fb('verified')} I Joined All", callback_data="check_join",
             style="success", icon_custom_emoji_id=_eid('verified'))
    b.adjust(1)
    return b.as_markup()


def try_again_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('refresh')} Try Again", callback_data="check_join",
             style="danger", icon_custom_emoji_id=_eid('refresh'))
    return b.as_markup()


# ═══════════════════════════════════════
# UTILITY KEYBOARDS
# ═══════════════════════════════════════

def back_keyboard(cb: str = "admin_back") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('back')} Back", callback_data=cb,
             style="primary", icon_custom_emoji_id=_eid('back'))
    return b.as_markup()


def error_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('menu')} Main Menu", callback_data="go_main_menu",
             style="primary", icon_custom_emoji_id=_eid('menu'))
    return b.as_markup()


# ═══════════════════════════════════════
# BALANCE / REFER KEYBOARDS
# ═══════════════════════════════════════

def refer_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('refer_menu')} My Referrals", callback_data="my_refer",
             style="success", icon_custom_emoji_id=_eid('refer_menu'))
    b.button(text=f"{_fb('trophy')} Top List", callback_data="top_lists",
             style="primary", icon_custom_emoji_id=_eid('trophy'))
    b.adjust(2)
    return b.as_markup()


def refer_back_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('back')} Back to Refer", callback_data="refer_back",
             style="primary", icon_custom_emoji_id=_eid('back'))
    return b.as_markup()


# ═══════════════════════════════════════
# SUPPORT KEYBOARD
# ═══════════════════════════════════════

def support_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=f"{_fb('user')} General Support",
        url=f"https://t.me/{GENERAL_SUPPORT_USERNAME}",
        style="primary",
        icon_custom_emoji_id=_eid('user'),
    )
    b.button(
        text=f"{_fb('crown')} Developer",
        url=f"https://t.me/{DEVELOPER_USERNAME.lstrip('@')}",
        style="success",
        icon_custom_emoji_id=_eid('crown'),
    )
    b.adjust(1)
    return b.as_markup()


# ═══════════════════════════════════════
# PROOFS KEYBOARD
# ═══════════════════════════════════════

def proofs_keyboard(channel_link: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('proofs')} View Proofs Channel", url=channel_link,
             style="primary", icon_custom_emoji_id=_eid('proofs'))
    return b.as_markup()


# ═══════════════════════════════════════
# GIFT CODE KEYBOARDS
# ═══════════════════════════════════════

def giftcode_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('gift')} Redeem Code", callback_data="open_redeem",
             style="success", icon_custom_emoji_id=_eid('gift'))
    return b.as_markup()


# ═══════════════════════════════════════
# ADMIN PANEL KEYBOARDS
# ═══════════════════════════════════════

def admin_panel_keyboard(is_master: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('botstats')} Stats",          callback_data="admin_stats",         style="primary", icon_custom_emoji_id=_eid('botstats'))
    b.button(text=f"{_fb('system')} System",           callback_data="admin_system",        style="primary", icon_custom_emoji_id=_eid('system'))
    b.button(text=f"{_fb('panel')} Panel Details",     callback_data="admin_panel_details", style="primary", icon_custom_emoji_id=_eid('panel'))
    b.button(text=f"{_fb('channel')} Force Sub",       callback_data="admin_force_sub",     style="success", icon_custom_emoji_id=_eid('channel'))
    b.button(text=f"{_fb('settings')} Settings",       callback_data="admin_settings",      style="primary", icon_custom_emoji_id=_eid('settings'))
    b.button(text=f"{_fb('key')} API Config",          callback_data="admin_api_config",    style="primary", icon_custom_emoji_id=_eid('key'))
    b.button(text=f"{_fb('broadcast')} Broadcast",     callback_data="admin_broadcast",     style="danger",  icon_custom_emoji_id=_eid('broadcast'))
    b.button(text=f"{_fb('gift')} Gift Codes",         callback_data="admin_codes",         style="success", icon_custom_emoji_id=_eid('gift'))
    b.button(text=f"{_fb('admins')} Manage Users",     callback_data="admin_users",         style="primary", icon_custom_emoji_id=_eid('admins'))
    b.button(text=f"{_fb('crown')} Admins",            callback_data="admin_admins",        style="primary", icon_custom_emoji_id=_eid('crown'))
    b.button(text=f"{_fb('instagram')} Images",        callback_data="admin_images",        style="primary", icon_custom_emoji_id=_eid('instagram'))
    b.button(text=f"{_fb('promo')} Messages",          callback_data="admin_messages",      style="success", icon_custom_emoji_id=_eid('promo'))
    b.button(text=f"{_fb('proofs')} Proof Channel",    callback_data="admin_proof_channel", style="primary", icon_custom_emoji_id=_eid('proofs'))
    b.button(text=f"{_fb('maintenance')} Maintenance", callback_data="admin_maintenance",   style="danger",  icon_custom_emoji_id=_eid('maintenance'))
    if is_master:
        b.button(text=f"{_fb('super')} Super Control", callback_data="admin_super_control", style="danger",  icon_custom_emoji_id=_eid('super'))
    b.adjust(2)
    return b.as_markup()


def admin_stats_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('stock')} Orders",    callback_data="admin_orders", style="primary", icon_custom_emoji_id=_eid('stock'))
    b.button(text=f"{_fb('refresh')} Refresh", callback_data="admin_stats",  style="success", icon_custom_emoji_id=_eid('refresh'))
    b.button(text=f"{_fb('back')} Back",       callback_data="admin_back",   style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2, 1)
    return b.as_markup()


def admin_system_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('refresh')} Refresh", callback_data="admin_system", style="success", icon_custom_emoji_id=_eid('refresh'))
    b.button(text=f"{_fb('back')} Back",       callback_data="admin_back",   style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2)
    return b.as_markup()


def admin_panel_details_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    services = [("followers", "Followers"), ("likes", "Likes"),
                ("views", "Views"), ("comments", "Comments")]
    for key, label in services:
        b.button(
            text=f"{_fb(key)} Set {label} Service",
            callback_data=f"admin_set_service_{key}",
            style="primary",
            icon_custom_emoji_id=_eid(key),
        )
    b.button(text=f"{_fb('back')} Back", callback_data="admin_back",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2)
    return b.as_markup()


def admin_force_sub_keyboard(channels: list = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('plus')} Add Channel",          callback_data="admin_add_channel",  style="success", icon_custom_emoji_id=_eid('plus'))
    b.button(text=f"{_fb('remove')} Clear All Channels", callback_data="admin_clear_channels", style="danger", icon_custom_emoji_id=_eid('remove'))
    b.adjust(2)
    # Per-channel remove buttons
    if channels:
        for ch in channels:
            cid     = ch.get("channel_id", 0)
            display = ch.get("display_name") or ch.get("channel_username", "?")
            b.button(
                text=f"{_fb('remove')} Remove: {display}",
                callback_data=f"admin_remove_channel_{cid}",
                style="danger",
                icon_custom_emoji_id=_eid('remove'),
            )
        b.adjust(2, *([1] * len(channels)))
    b.button(text=f"{_fb('back')} Back", callback_data="admin_back",
             style="primary", icon_custom_emoji_id=_eid('back'))
    return b.as_markup()


def admin_image_manager_keyboard(screens: list, images: dict = None) -> InlineKeyboardMarkup:
    """images is an optional dict mapping screen_name -> file_id (truthy = set)."""
    if images is None:
        images = {}
    b = InlineKeyboardBuilder()
    for screen in screens:
        has = bool(images.get(screen))
        b.button(
            text=f"{_fb('check') if has else _fb('error')} {screen.capitalize()}",
            callback_data=f"imgmgr_{screen}",
            style="success" if has else "primary",
            icon_custom_emoji_id=_eid('check') if has else _eid('error'),
        )
    b.button(text=f"{_fb('back')} Back", callback_data="admin_back",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2)
    return b.as_markup()


def admin_image_actions_keyboard(screen: str, has_image: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('plus')} Upload Image", callback_data=f"imgset_{screen}",
             style="success", icon_custom_emoji_id=_eid('plus'))
    if has_image:
        b.button(text=f"{_fb('remove')} Remove Image", callback_data=f"imgdel_{screen}",
                 style="danger", icon_custom_emoji_id=_eid('remove'))
    b.button(text=f"{_fb('back')} Back", callback_data="admin_images",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2 if has_image else 1, 1)
    return b.as_markup()


def admin_ban_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('ban')} Ban User",       callback_data="admin_ban_user",   style="danger",  icon_custom_emoji_id=_eid('ban'))
    b.button(text=f"{_fb('success')} Unban User", callback_data="admin_unban_user", style="success", icon_custom_emoji_id=_eid('success'))
    b.button(text=f"{_fb('back')} Back",          callback_data="admin_users",      style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2, 1)
    return b.as_markup()


def admin_bonus_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('bonus')} Give Bonus (User)", callback_data="admin_bonus_user", style="success", icon_custom_emoji_id=_eid('bonus'))
    b.button(text=f"{_fb('sparkle')} Give Bonus (All)", callback_data="admin_bonus_all", style="primary", icon_custom_emoji_id=_eid('sparkle'))
    b.button(text=f"{_fb('back')} Back",                callback_data="admin_users",     style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2, 1)
    return b.as_markup()


def admin_admins_keyboard(admins: list, master_admin_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('plus')} Add Admin",      callback_data="admin_add_admin",    style="success", icon_custom_emoji_id=_eid('plus'))
    b.button(text=f"{_fb('remove')} Remove Admin", callback_data="admin_remove_admin", style="danger",  icon_custom_emoji_id=_eid('remove'))
    b.button(text=f"{_fb('back')} Back",           callback_data="admin_back",         style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2, 1)
    return b.as_markup()


def admin_api_config_keyboard(has_key: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('key')} Set API Key",   callback_data="admin_set_api_key",    style="success", icon_custom_emoji_id=_eid('key'))
    b.button(text=f"{_fb('link')} Set API URL",  callback_data="admin_set_api_url",    style="primary", icon_custom_emoji_id=_eid('link'))
    if has_key:
        b.button(text=f"{_fb('remove')} Delete Key", callback_data="admin_delete_api_key", style="danger", icon_custom_emoji_id=_eid('remove'))
    b.button(text=f"{_fb('back')} Back", callback_data="admin_back",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2)
    return b.as_markup()


def admin_proof_channel_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('id')} Set Channel ID",    callback_data="admin_set_proof_channel_id",   style="primary", icon_custom_emoji_id=_eid('id'))
    b.button(text=f"{_fb('link')} Set Channel Link",callback_data="admin_set_proof_channel_link", style="success", icon_custom_emoji_id=_eid('link'))
    b.button(text=f"{_fb('back')} Back",             callback_data="admin_back",                  style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2, 1)
    return b.as_markup()


def admin_messages_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('promo')} Edit Promo Message",   callback_data="admin_edit_promo",        style="primary", icon_custom_emoji_id=_eid('promo'))
    b.button(text=f"{_fb('menu')} Edit Menu Message",     callback_data="admin_edit_menu",          style="success", icon_custom_emoji_id=_eid('menu'))
    b.button(text=f"{_fb('refresh')} Toggle Promo Mode",  callback_data="admin_toggle_promo_mode",  style="danger",  icon_custom_emoji_id=_eid('refresh'))
    b.button(text=f"{_fb('remove')} Reset Promo",         callback_data="admin_reset_promo",        style="danger",  icon_custom_emoji_id=_eid('remove'))
    b.button(text=f"{_fb('remove')} Reset Menu",          callback_data="admin_reset_menu",         style="danger",  icon_custom_emoji_id=_eid('remove'))
    b.button(text=f"{_fb('back')} Back",                  callback_data="admin_back",               style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2, 1, 2, 1)
    return b.as_markup()


def admin_messages_confirm_reset_keyboard(target: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('remove')} Yes, Reset", callback_data=f"admin_confirm_reset_{target}",
             style="danger", icon_custom_emoji_id=_eid('remove'))
    b.button(text=f"{_fb('back')} No, Cancel",   callback_data="admin_messages",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2)
    return b.as_markup()


def admin_settings_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('balance_menu')} Min Withdraw Pts", callback_data="setting_min_withdraw",     style="primary", icon_custom_emoji_id=_eid('balance_menu'))
    b.button(text=f"{_fb('refer_menu')} Pts per Refer",      callback_data="setting_points_per_refer",  style="success", icon_custom_emoji_id=_eid('refer_menu'))
    b.button(text=f"{_fb('followers')} Followers Ratio",     callback_data="setting_followers_ratio",   style="primary", icon_custom_emoji_id=_eid('followers'))
    b.button(text=f"{_fb('likes')} Likes Ratio",             callback_data="setting_likes_ratio",       style="success", icon_custom_emoji_id=_eid('likes'))
    b.button(text=f"{_fb('views')} Views Ratio",             callback_data="setting_views_ratio",       style="primary", icon_custom_emoji_id=_eid('views'))
    b.button(text=f"{_fb('comments')} Comments Ratio",       callback_data="setting_comments_ratio",    style="success", icon_custom_emoji_id=_eid('comments'))
    b.button(text=f"{_fb('captcha')} Captcha",               callback_data="setting_toggle_captcha",    style="danger",  icon_custom_emoji_id=_eid('captcha'))
    b.button(text=f"{_fb('back')} Back",                     callback_data="admin_back",               style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2, 2, 2, 1, 1)
    return b.as_markup()


def admin_captcha_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    label = "Turn OFF Captcha" if enabled else "Turn ON Captcha"
    style = "danger" if enabled else "success"
    icon  = _eid('captcha')
    b.button(text=f"{_fb('captcha')} {label}", callback_data="setting_toggle_captcha",
             style=style, icon_custom_emoji_id=icon)
    b.button(text=f"{_fb('back')} Back", callback_data="admin_settings",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(1)
    return b.as_markup()


# ═══════════════════════════════════════
# ORDERS KEYBOARDS
# ═══════════════════════════════════════

def admin_pending_orders_keyboard(orders: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for order in orders[:20]:
        oid   = str(order.get("id") or order.get("_id", ""))
        svc   = order.get("service", "?")
        qty   = order.get("quantity", "?")
        uid   = order.get("user_id", "?")
        label = f"#{oid[:6]} {svc} ×{qty} (uid:{uid})"
        b.button(text=label, callback_data=f"admin_order_{oid}", style="primary")
    b.button(text=f"{_fb('back')} Back", callback_data="admin_back",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(1)
    return b.as_markup()


def admin_order_detail_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Detail view for a single order — no approve/reject since orders auto-place."""
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('refresh')} Refresh Status", callback_data=f"admin_order_{order_id}",
             style="success", icon_custom_emoji_id=_eid('refresh'))
    b.button(text=f"{_fb('back')} Back to Orders",    callback_data="admin_orders",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(1)
    return b.as_markup()


# ═══════════════════════════════════════
# WITHDRAW KEYBOARDS
# ═══════════════════════════════════════

def withdraw_service_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('followers')} Followers", callback_data="withdraw_followers", style="primary", icon_custom_emoji_id=_eid('followers'))
    b.button(text=f"{_fb('likes')} Likes",         callback_data="withdraw_likes",     style="success", icon_custom_emoji_id=_eid('likes'))
    b.button(text=f"{_fb('views')} Views",          callback_data="withdraw_views",     style="primary", icon_custom_emoji_id=_eid('views'))
    b.button(text=f"{_fb('comments')} Comments",   callback_data="withdraw_comments",  style="success", icon_custom_emoji_id=_eid('comments'))
    b.button(text=f"{_fb('cancel')} Cancel",        callback_data="cancel_withdraw",    style="danger",  icon_custom_emoji_id=_eid('cancel'))
    b.adjust(2, 2, 1)
    return b.as_markup()


def cancel_withdraw_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('cancel')} Cancel", callback_data="cancel_withdraw",
             style="danger", icon_custom_emoji_id=_eid('cancel'))
    return b.as_markup()


def preview_continue_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('success')} Continue", callback_data="preview_continue",
             style="success", icon_custom_emoji_id=_eid('success'))
    b.button(text=f"{_fb('cancel')} Cancel",    callback_data="cancel_withdraw",
             style="danger",  icon_custom_emoji_id=_eid('cancel'))
    b.adjust(2)
    return b.as_markup()


def preview_private_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('cancel')} Cancel Order", callback_data="cancel_withdraw",
             style="danger", icon_custom_emoji_id=_eid('cancel'))
    return b.as_markup()


def skip_proof_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('back')} Skip Proof", callback_data="skip_proof",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.button(text=f"{_fb('cancel')} Cancel",   callback_data="cancel_withdraw",
             style="danger",  icon_custom_emoji_id=_eid('cancel'))
    b.adjust(2)
    return b.as_markup()


def check_order_keyboard(order_id: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=f"{_fb('refresh')} Check Status",
        callback_data=f"check_order_{order_id}",
        style="success",
        icon_custom_emoji_id=_eid('refresh'),
    )
    return b.as_markup()


# ═══════════════════════════════════════
# MAINTENANCE KEYBOARD
# ═══════════════════════════════════════

def maintenance_keyboard(is_on: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if is_on:
        b.button(text=f"{_fb('success')} Turn OFF Maintenance", callback_data="maintenance_toggle",
                 style="success", icon_custom_emoji_id=_eid('success'))
    else:
        b.button(text=f"{_fb('maintenance')} Turn ON Maintenance", callback_data="maintenance_toggle",
                 style="danger", icon_custom_emoji_id=_eid('maintenance'))
    b.button(text=f"{_fb('back')} Back", callback_data="admin_back",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(1)
    return b.as_markup()


# ═══════════════════════════════════════
# SUPER CONTROL KEYBOARD  (master admin only)
# ═══════════════════════════════════════

def super_control_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('logs')} Live Logs",           callback_data="sc_logs",          style="primary", icon_custom_emoji_id=_eid('logs'))
    b.button(text=f"{_fb('reboot')} Soft Reboot",       callback_data="sc_reboot",        style="danger",  icon_custom_emoji_id=_eid('reboot'))
    b.button(text=f"{_fb('token')} Change Bot Token",   callback_data="sc_change_token",  style="danger",  icon_custom_emoji_id=_eid('token'))
    b.button(text=f"{_fb('github')} Check Latest Push", callback_data="sc_latest_push",   style="success", icon_custom_emoji_id=_eid('github'))
    b.button(text=f"{_fb('back')} Back",                callback_data="admin_back",        style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2, 2, 1)
    return b.as_markup()


def sc_confirm_reboot_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('reboot')} Yes, Reboot Now", callback_data="sc_confirm_reboot",
             style="danger", icon_custom_emoji_id=_eid('reboot'))
    b.button(text=f"{_fb('back')} Cancel",            callback_data="admin_super_control",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2)
    return b.as_markup()


def sc_push_confirm_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('success')} Confirm Push & Restart", callback_data="sc_confirm_push",
             style="success", icon_custom_emoji_id=_eid('success'))
    b.button(text=f"{_fb('cancel')} Cancel",                  callback_data="admin_super_control",
             style="danger",  icon_custom_emoji_id=_eid('cancel'))
    b.adjust(1)
    return b.as_markup()


# ═══════════════════════════════════════
# ADMIN USERS KEYBOARD (sub-menu for user management)
# ═══════════════════════════════════════

def admin_gift_codes_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for the admin gift codes panel."""
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('gift')} Create Code", callback_data="admin_create_code",
             style="success", icon_custom_emoji_id=_eid('gift'))
    b.button(text=f"{_fb('remove')} Delete Code", callback_data="admin_delete_code",
             style="danger", icon_custom_emoji_id=_eid('remove'))
    b.button(text=f"{_fb('back')} Back", callback_data="admin_back",
             style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2, 1)
    return b.as_markup()


def service_scope_keyboard(svc: str) -> InlineKeyboardMarkup:
    """Keyboard to pick single-post vs all-posts scope for likes/comments service."""
    b = InlineKeyboardBuilder()
    b.button(
        text=f"{_fb('single_post')} Single Post (post/reel URL)",
        callback_data=f"scope_single_{svc}",
        style="primary",
        icon_custom_emoji_id=_eid('single_post'),
    )
    b.button(
        text=f"{_fb('all_posts')} All Posts on Account (profile URL)",
        callback_data=f"scope_all_{svc}",
        style="success",
        icon_custom_emoji_id=_eid('all_posts'),
    )
    b.adjust(1)
    return b.as_markup()


def admin_users_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_fb('ban')} Ban / Unban",         callback_data="admin_ban_user",   style="danger",  icon_custom_emoji_id=_eid('ban'))
    b.button(text=f"{_fb('bonus')} Give Bonus",        callback_data="admin_bonus_user", style="success", icon_custom_emoji_id=_eid('bonus'))
    b.button(text=f"{_fb('sparkle')} Bonus All Users", callback_data="admin_bonus_all",  style="primary", icon_custom_emoji_id=_eid('sparkle'))
    b.button(text=f"{_fb('back')} Back",               callback_data="admin_back",       style="primary", icon_custom_emoji_id=_eid('back'))
    b.adjust(2, 1, 1)
    return b.as_markup()
