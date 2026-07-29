"""
handlers/emoji.py — /add and /apply commands for bulk emoji management.
Master admin only.

BUG FIX: The previous bare @router.message(F.text | F.caption) handler
had NO state filter and NO upfront user-ID filter.  Because this router
was included before all others in main.py, it swallowed EVERY text message
from every user — /start, menu button presses, everything — returning None
for non-admins and silently eating the update.

Fix: /add now sets EmojiStates.awaiting_emoji_input, and the collection
handler is scoped to that state.  Non-master messages never reach it at all.
"""

import json
import logging
import re

from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from config import MASTER_ADMIN_ID
from emojis import e, divider, PREMIUM

logger = logging.getLogger(__name__)
router = Router()

# Semantic auto-naming map  fallback char → key name
AUTO_NAME_MAP: dict[str, str] = {
    "🦋": "butterfly", "✅": "check",   "⚠️": "warning", "❌": "error",
    "👑": "crown",      "🔑": "key",     "❤️": "likes",   "👥": "followers",
    "👁": "views",       "💬": "comments","📊": "stats",   "💎": "diamond",
    "🎁": "gift",        "🏆": "trophy",  "🚀": "rocket",  "🔥": "fire",
    "⭐": "star",        "✨": "sparkle", "📸": "instagram","💰": "money",
    "💸": "points",      "💳": "withdraw","🔗": "link",    "📢": "channel",
    "⏳": "loading",     "🔄": "refresh", "◀️": "back",
    "➕": "plus",        "🗑": "remove",  "📤": "send",
    "🛡": "admin",       "🎉": "promo",   "💡": "tip",     "🟢": "live",
    "📋": "proofs",      "🆘": "support", "🧠": "brain",   "🎯": "earn",
    "📈": "botstats",    "⚙️": "settings","💻": "system",  "📢": "broadcast",
    "📦": "stock",       "🌸": "flower",  "🎀": "ribbon",  "🔧": "maintenance",
    "👤": "user",        "🆔": "id",
}


class EmojiStates(StatesGroup):
    awaiting_emoji_input = State()   # waiting for user to send emoji-containing message
    naming_single        = State()   # stepping through emojis one-by-one for manual naming


# ─── helpers ─────────────────────────────────────────────────────────────────

def _is_master(user_id: int) -> bool:
    return user_id == MASTER_ADMIN_ID


async def _get_overrides() -> dict:
    """Fetch current emoji overrides from DB."""
    raw = await db.get_setting("premium_emojis", "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


async def _save_overrides(overrides: dict) -> None:
    await db.set_setting("premium_emojis", json.dumps(overrides))


def _extract_custom_emojis(text: str, entities) -> list[dict]:
    """Extract custom emoji IDs and fallback chars from a message."""
    found = []
    seen  = set()
    for ent in (entities or []):
        if ent.type == "custom_emoji":
            eid = str(ent.custom_emoji_id)
            if eid in seen:
                continue
            seen.add(eid)
            start = ent.offset
            end   = start + ent.length
            encoded = text.encode("utf-16-le")
            fallback = encoded[start * 2 : end * 2].decode("utf-16-le", errors="replace")
            found.append({"id": eid, "fallback": fallback or "•"})
    return found


def _naming_keyboard() -> object:
    b = InlineKeyboardBuilder()
    b.button(text="Auto-Name All", callback_data="emgr_autoname")
    b.button(text="Name Manually", callback_data="emgr_name_next")
    b.button(text="Cancel",        callback_data="emgr_cancel")
    b.adjust(2, 1)
    return b.as_markup()


# ─── /add ─────────────────────────────────────────────────────────────────────

@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    if not _is_master(message.from_user.id):
        return
    await state.clear()
    # ← KEY FIX: set state so the collection handler ONLY fires for master in this state
    await state.set_state(EmojiStates.awaiting_emoji_input)
    await message.answer(
        f"{e('tip')} <b>Send a message containing premium emojis.</b>\n"
        f"{divider()}"
        f"I will extract all custom emoji IDs from it.",
        parse_mode="HTML",
    )


# ─── COLLECTION HANDLER ───────────────────────────────────────────────────────
# FIXED: requires EmojiStates.awaiting_emoji_input AND master admin check.
# Previously this had NO state filter and swallowed every text message globally.

@router.message(
    StateFilter(EmojiStates.awaiting_emoji_input),
    F.from_user.func(lambda u: u.id == MASTER_ADMIN_ID),
    F.text | F.caption,
)
async def handle_emoji_collection_msg(message: Message, state: FSMContext):
    """Collect custom emojis from a message — master admin only, gated by FSM state."""
    try:
        text     = message.text or message.caption or ""
        entities = message.entities or message.caption_entities or []
        found    = _extract_custom_emojis(text, entities)

        if not found:
            await message.answer(
                f"{e('warning')} No premium emojis found in that message.\n"
                f"Send another message with custom animated emojis, or /add to restart.",
                parse_mode="HTML",
            )
            return

        # Store found emojis in FSM data for naming flow
        await state.update_data(found_emojis=found, naming_index=0)

        summary = "\n".join(
            f"  {i+1}. ID <code>{f['id']}</code>  fallback: {f['fallback']}"
            for i, f in enumerate(found)
        )
        await message.answer(
            f"{e('sparkle')} <b>Found {len(found)} premium emoji(s):</b>\n"
            f"{divider()}"
            f"{summary}\n"
            f"{divider()}"
            f"Choose how to name them:",
            parse_mode="HTML",
            reply_markup=_naming_keyboard(),
        )
    except Exception as ex:
        logger.error(f"handle_emoji_collection_msg uid={message.from_user.id}: {ex}", exc_info=True)


# ─── Auto-Name ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "emgr_autoname")
async def cb_emgr_autoname(callback: CallbackQuery, state: FSMContext):
    if not _is_master(callback.from_user.id):
        await callback.answer()
        return
    try:
        await callback.answer("Auto-naming…")
        data  = await state.get_data()
        found = data.get("found_emojis", [])
        if not found:
            await callback.message.answer(
                f"{e('warning')} No emoji data in session. Run /add again.",
                parse_mode="HTML",
            )
            return

        overrides = await _get_overrides()
        named     = []
        unnamed   = []

        for item in found:
            fb  = item["fallback"]
            eid = item["id"]
            key = AUTO_NAME_MAP.get(fb)
            if key:
                overrides[key] = [eid, fb]
                named.append(f"  {e('check')} <code>{key}</code> ← {fb}")
            else:
                unnamed.append(f"  {e('warning')} ID <code>{eid}</code> fallback {fb!r} — not in map")

        await _save_overrides(overrides)
        await state.clear()

        summary = "\n".join(named + unnamed) or "<i>nothing to save</i>"
        await callback.message.answer(
            f"{e('success')} <b>Auto-named {len(named)} emoji(s).</b>\n"
            f"{divider()}"
            f"{summary}\n"
            f"{divider()}"
            f"Run <b>/apply</b> to make them live.",
            parse_mode="HTML",
        )
    except Exception as ex:
        logger.error(f"cb_emgr_autoname uid={callback.from_user.id}: {ex}", exc_info=True)


# ─── Manual Naming ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "emgr_name_next")
async def cb_emgr_name_next(callback: CallbackQuery, state: FSMContext):
    """Start or continue manual naming — prompt admin for each emoji's key name."""
    if not _is_master(callback.from_user.id):
        await callback.answer()
        return
    try:
        await callback.answer()
        data   = await state.get_data()
        found  = data.get("found_emojis", [])
        index  = data.get("naming_index", 0)

        if not found or index >= len(found):
            await callback.message.answer(
                f"{e('warning')} No emoji data. Run /add again.",
                parse_mode="HTML",
            )
            await state.clear()
            return

        item = found[index]
        await state.set_state(EmojiStates.naming_single)
        await callback.message.answer(
            f"{e('tip')} <b>Name Manually — {index + 1}/{len(found)}</b>\n"
            f"{divider()}"
            f"Emoji ID: <code>{item['id']}</code>  fallback: {item['fallback']}\n\n"
            f"Type a unique key name for this emoji (e.g. <code>crown</code>, <code>fire</code>).\n"
            f"Type <b>skip</b> to leave this one unnamed.",
            parse_mode="HTML",
        )
    except Exception as ex:
        logger.error(f"cb_emgr_name_next uid={callback.from_user.id}: {ex}", exc_info=True)


@router.message(
    StateFilter(EmojiStates.naming_single),
    F.from_user.func(lambda u: u.id == MASTER_ADMIN_ID),
    F.text,
)
async def handle_manual_name_input(message: Message, state: FSMContext):
    """Receive the key name typed by admin and step to next emoji."""
    try:
        data      = await state.get_data()
        found     = data.get("found_emojis", [])
        index     = data.get("naming_index", 0)
        overrides = await _get_overrides()

        if not found or index >= len(found):
            await state.clear()
            return

        item      = found[index]
        raw_name  = (message.text or "").strip().lower()

        if raw_name == "skip":
            feedback = f"{e('warning')} Skipped ID <code>{item['id']}</code>"
        elif not re.match(r"^[a-z0-9_]+$", raw_name):
            await message.answer(
                f"{e('error')} Key name must be lowercase letters, digits, or underscores only. Try again:",
                parse_mode="HTML",
            )
            return
        elif raw_name in overrides:
            await message.answer(
                f"{e('error')} Key <code>{raw_name}</code> already exists. Choose a different name:",
                parse_mode="HTML",
            )
            return
        else:
            overrides[raw_name] = [item["id"], item["fallback"]]
            await _save_overrides(overrides)
            feedback = f"{e('success')} Saved <code>{raw_name}</code> ← {item['fallback']}"

        next_index = index + 1
        await state.update_data(naming_index=next_index)

        if next_index >= len(found):
            await state.clear()
            await message.answer(
                f"{feedback}\n\n"
                f"{e('check')} <b>All emojis processed!</b>\n"
                f"Run <b>/apply</b> to make them live.",
                parse_mode="HTML",
            )
        else:
            next_item = found[next_index]
            await state.set_state(EmojiStates.naming_single)
            await message.answer(
                f"{feedback}\n\n"
                f"{e('tip')} <b>Next — {next_index + 1}/{len(found)}</b>\n"
                f"{divider()}"
                f"Emoji ID: <code>{next_item['id']}</code>  fallback: {next_item['fallback']}\n\n"
                f"Type a key name or <b>skip</b>:",
                parse_mode="HTML",
            )
    except Exception as ex:
        logger.error(f"handle_manual_name_input uid={message.from_user.id}: {ex}", exc_info=True)


# ─── Cancel ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "emgr_cancel")
async def cb_emgr_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Cancelled.")
    await callback.message.answer(f"{e('cancel')} Emoji collection cancelled.", parse_mode="HTML")


# ─── /apply ───────────────────────────────────────────────────────────────────

@router.message(Command("apply"))
async def cmd_apply(message: Message, bot: Bot):
    if not _is_master(message.from_user.id):
        return
    try:
        overrides = await _get_overrides()
        if not overrides:
            await message.answer(
                f"{e('warning')} No saved emoji overrides to apply. Use /add first.",
                parse_mode="HTML",
            )
            return

        import emojis as _em
        for k, v in overrides.items():
            if isinstance(v, str):
                fb = PREMIUM.get(k, ("", "•"))[1]
                _em.PREMIUM[k] = (v, fb)
            elif isinstance(v, (list, tuple)) and len(v) >= 2:
                _em.PREMIUM[k] = (str(v[0]), str(v[1]))

        _em._OVERRIDE.clear()

        await message.answer(
            f"{e('success')} <b>{len(overrides)} emojis applied live!</b>\n"
            f"{e('tip')} Changes take effect immediately — no restart needed.",
            parse_mode="HTML",
        )
    except Exception as ex:
        logger.error(f"cmd_apply uid={message.from_user.id}: {ex}", exc_info=True)
