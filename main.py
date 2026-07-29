"""
main.py — Bot entry point.
Features:
  • Log buffer (last 100 lines) accessible via Super Control
  • Maintenance mode middleware — non-admins see a maintenance message
  • Permission middleware — ban check, force reverify, verified gate
  • Auto soft-reboot on fatal errors
  • Startup notification to master admin
  • Health check HTTP server (aiohttp) — for Replit Reserved VM / UptimeRobot
  • delete_webhook() called on every startup — prevents stale webhook from blocking polling
"""

import asyncio
import collections
import json
import logging
import os
import sys

# ─── ensure project root is on sys.path ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ─────────────────────────────────────────────────────────────────────────────

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject, Message, CallbackQuery, BotCommand
from typing import Callable, Dict, Any, Awaitable

import database as db
from config import BOT_TOKEN, BOT_NAME, MASTER_ADMIN_ID, ORDER_CHECK_INTERVAL, LOG_BUFFER_SIZE
from emojis import e, divider, update_override

from handlers import start, balance, refer, stock, support, proofs, giftcode, withdraw, admin
from handlers import emoji as emoji_handler
from api.jap import jap

# ═══════════════════════════════════════
# LOG BUFFER  (exported for Super Control)
# ═══════════════════════════════════════

_LOG_BUFFER: collections.deque = collections.deque(maxlen=LOG_BUFFER_SIZE)


class _LogBufferHandler(logging.Handler):
    """Captures log records into the in-memory deque."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            _LOG_BUFFER.append(line)
        except Exception:
            pass


# ── Configure logging ─────────────────────────────────────────────────────────

_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_fmt)

_buf_handler = _LogBufferHandler()
_buf_handler.setFormatter(_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_stream_handler, _buf_handler])
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════
# HEALTH CHECK HTTP SERVER
# ═══════════════════════════════════════

async def _run_health_server() -> None:
    """Minimal aiohttp health check server bound to PORT env var (default 8080).
    Returns 200 OK for GET / and GET /health.
    This keeps the process compatible with Replit Reserved VM health checks
    and UptimeRobot without interfering with polling."""
    try:
        from aiohttp import web

        async def _ok(request):
            return web.Response(text="OK", status=200)

        app  = web.Application()
        app.router.add_get("/", _ok)
        app.router.add_get("/health", _ok)

        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Health check server listening on :{port}")
    except Exception as ex:
        logger.warning(f"Health server failed to start: {ex} (non-fatal, polling continues)")


# ═══════════════════════════════════════
# MAINTENANCE MIDDLEWARE
# ═══════════════════════════════════════

def _extract_user_from_update(event: TelegramObject):
    from aiogram.types import Update
    if isinstance(event, Update):
        if event.message:
            return event.message.from_user
        if event.callback_query:
            return event.callback_query.from_user
        if event.edited_message:
            return event.edited_message.from_user
        if event.channel_post:
            return event.channel_post.from_user
    if isinstance(event, (Message, CallbackQuery)):
        return event.from_user
    if hasattr(event, "from_user"):
        return event.from_user
    return None


def _extract_inner_event(event: TelegramObject):
    from aiogram.types import Update
    if isinstance(event, Update):
        return event.message or event.callback_query or event.edited_message
    return event


class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user  = _extract_user_from_update(event)
        inner = _extract_inner_event(event)

        if user is None:
            return await handler(event, data)

        if user.id == MASTER_ADMIN_ID:
            return await handler(event, data)

        if await db.is_admin(user.id, MASTER_ADMIN_ID):
            return await handler(event, data)

        if await db.is_maintenance():
            msg = (
                f"{e('maintenance')} <b>Bot is under maintenance.</b>\n"
                f"{divider()}"
                f"{e('tip')} We're making improvements and will be back shortly."
            )
            if isinstance(inner, Message):
                await inner.answer(msg, parse_mode="HTML")
            elif isinstance(inner, CallbackQuery):
                await inner.answer("Bot is under maintenance.", show_alert=True)
            return


# ═══════════════════════════════════════
# PERMISSION MIDDLEWARE
# ═══════════════════════════════════════

class PermissionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user  = _extract_user_from_update(event)
        inner = _extract_inner_event(event)

        if user is None:
            return await handler(event, data)

        if user.id == MASTER_ADMIN_ID:
            return await handler(event, data)

        try:
            db_user = await db.get_user(user.id)
            if not db_user:
                return await handler(event, data)

            bot: Bot = data["bot"]

            if db_user["is_banned"]:
                msg = (
                    f"{e('ban')} <b>You are banned from this bot.</b>\n"
                    f"{divider()}"
                    f"Contact support if this is a mistake."
                )
                if isinstance(inner, Message):
                    await inner.answer(msg, parse_mode="HTML")
                elif isinstance(inner, CallbackQuery):
                    await inner.answer("You are banned.", show_alert=True)
                return

            force_rev = await db.get_setting("force_reverify", "0")
            if force_rev == "1" and db_user["is_verified"]:
                await db.set_user_verified(user.id, 0)
                db_user = await db.get_user(user.id)

            is_start = (
                isinstance(inner, Message)
                and inner.text
                and inner.text.startswith("/start")
            )
            is_join_cb = (
                isinstance(inner, CallbackQuery)
                and inner.data in ("check_join", "continue_promo")
            )

            if not db_user["is_verified"] and not is_start and not is_join_cb:
                channels = await db.get_all_channels()
                if channels:
                    from handlers.start import _show_force_join
                    try:
                        if isinstance(inner, Message):
                            await _show_force_join(bot, inner.chat.id, channels)
                        elif isinstance(inner, CallbackQuery):
                            await inner.answer(
                                "Please join all channels first!", show_alert=True,
                            )
                    except Exception:
                        pass
                    return
                else:
                    await db.set_user_verified(user.id, 1)

        except Exception as ex:
            logger.error(f"PermissionMiddleware: {ex}", exc_info=True)

        return await handler(event, data)


# ═══════════════════════════════════════
# BACKGROUND ORDER CHECKER
# ═══════════════════════════════════════

async def order_checker_task(bot: Bot) -> None:
    """Periodically check pending orders and refund on Cancelled/Failed."""
    while True:
        try:
            await asyncio.sleep(ORDER_CHECK_INTERVAL)
            orders = await db.get_pending_orders()
            for order in orders:
                try:
                    jap_id = order.get("jap_order_id", "")
                    if not jap_id:
                        continue
                    status_info = await jap.check_status(jap_id)
                    if not status_info:
                        continue
                    status = status_info.get("status", "")
                    if status:
                        order_id = order["id"]
                        await db.update_order_status(order_id, status)

                    if status in ("Cancelled", "Failed", "cancelled", "failed"):
                        pts = order.get("points_spent", 0)
                        if pts and pts > 0 and not order.get("refunded"):
                            await db.add_points(order["user_id"], pts)
                            await db.mark_order_refunded(order["id"])
                            try:
                                await bot.send_message(
                                    order["user_id"],
                                    f"{e('bonus')} <b>Order refunded!</b>\n"
                                    f"Order <code>#{jap_id}</code> was {status}.\n"
                                    f"{e('points')} <b>+{pts} pts</b> returned to your balance.",
                                    parse_mode="HTML",
                                )
                            except Exception:
                                pass
                except Exception as ex:
                    logger.error(f"order_checker order={order.get('id','?')}: {ex}")
        except asyncio.CancelledError:
            break
        except Exception as ex:
            logger.error(f"order_checker_task: {ex}", exc_info=True)


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp  = Dispatcher(storage=MemoryStorage())

    # ── Database ────────────────────────────────────────────────────
    await db.init_db()
    logger.info("Database initialized.")

    # ── Load emoji overrides from DB ─────────────────────────────────
    try:
        import json as _json
        raw = await db.get_setting("premium_emojis", "")
        if raw:
            update_override(_json.loads(raw))
    except Exception as ex:
        logger.warning(f"Failed to load emoji overrides: {ex}")

    # ── Middlewares ──────────────────────────────────────────────────
    dp.update.outer_middleware(MaintenanceMiddleware())
    dp.update.outer_middleware(PermissionMiddleware())

    # ── Routers — CRITICAL ORDER:
    #    1. admin first (command-based, no ambiguity)
    #    2. emoji AFTER admin, but its handlers are all state-gated now
    #    3. start handles /start, /help, and the "Main Menu" button
    #    4. All menu-button handlers (exact text match, no overlap)
    #    5. withdraw last (has its own exact BTN_WITHDRAW filter now)
    dp.include_router(admin.router)
    dp.include_router(emoji_handler.router)
    dp.include_router(start.router)
    dp.include_router(balance.router)
    dp.include_router(refer.router)
    dp.include_router(stock.router)
    dp.include_router(support.router)
    dp.include_router(proofs.router)
    dp.include_router(giftcode.router)
    dp.include_router(withdraw.router)

    # ── Bot commands menu ────────────────────────────────────────────
    me = await bot.get_me()
    try:
        await bot.set_my_commands([
            BotCommand(command="start",  description="Start the bot"),
            BotCommand(command="help",   description="Show help"),
            BotCommand(command="redeem", description="Redeem a gift code"),
            BotCommand(command="admin",  description="Admin panel"),
        ])
    except Exception as ex:
        logger.warning(f"set_my_commands: {ex}")

    # ── Health check HTTP server (runs in background) ─────────────────
    asyncio.create_task(_run_health_server())

    # ── Background order checker ──────────────────────────────────────
    checker = asyncio.create_task(order_checker_task(bot))
    logger.info(f"Order checker running every {ORDER_CHECK_INTERVAL}s.")

    # ── Startup notification ──────────────────────────────────────────
    try:
        maint = await db.is_maintenance()
        await bot.send_message(
            MASTER_ADMIN_ID,
            f"{e('success')} <b>Bot Started!</b>\n"
            f"{divider()}"
            f"{e('instagram')} @{me.username}\n"
            f"{e('maintenance')} Maintenance: <b>{'ON' if maint else 'OFF'}</b>\n"
            f"{e('crown')} /admin",
            parse_mode="HTML",
        )
    except Exception as ex:
        logger.warning(f"Startup notification: {ex}")

    logger.info(f"Bot @{me.username} is live.")

    # ── Delete any pre-existing webhook BEFORE polling ────────────────
    # CRITICAL: If a webhook was ever set on this token (even once, months ago),
    # Telegram will keep routing ALL updates to that webhook URL instead of to
    # our polling loop — causing the bot to appear alive but receive nothing.
    # This single line prevents that permanently on every startup.
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook cleared — polling mode active.")
    except Exception as ex:
        logger.warning(f"delete_webhook: {ex}")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        checker.cancel()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as ex:
        logger.critical(f"Fatal error: {ex}", exc_info=True)
        import time
        time.sleep(3)
        os.execv(sys.executable, [sys.executable] + sys.argv)
