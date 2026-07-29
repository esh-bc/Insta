"""
database.py — Async MongoDB database layer.
All operations are async. Data lives in MongoDB Atlas (survives host migrations).
"""

import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

import motor.motor_asyncio

from config import MONGODB_URI, DEFAULT_SETTINGS

# ═══════════════════════════════════════
# CLIENT & COLLECTIONS
# ═══════════════════════════════════════

_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
_db = None


def _get_db():
    global _client, _db
    if _db is None:
        _client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
        _db = _client["instagram_bot"]
    return _db


def col(name: str):
    return _get_db()[name]


# ═══════════════════════════════════════
# DOCUMENT NORMALIZATION
# ═══════════════════════════════════════

def _norm(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


def _norm_list(docs: list) -> list:
    return [_norm(d) for d in docs]


# ═══════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════

async def init_db() -> None:
    """Create indexes and seed default settings."""
    db = _get_db()

    await db["users"].create_index("telegram_id", unique=True)
    await db["users"].create_index("referral_code", unique=True, sparse=True)
    await db["users"].create_index("username")
    await db["users"].create_index("created_at")
    await db["referrals"].create_index([("referrer_id", 1), ("referred_id", 1)], unique=True)
    await db["orders"].create_index("user_id")
    await db["orders"].create_index("status")
    await db["orders"].create_index("created_at")
    await db["orders"].create_index([("user_id", 1), ("instagram_link", 1), ("service", 1), ("created_at", -1)])
    await db["gift_codes"].create_index("code", unique=True)
    await db["code_redemptions"].create_index([("code", 1), ("user_id", 1)], unique=True)
    await db["admins"].create_index("user_id", unique=True)
    await db["force_channels"].create_index("channel_id", unique=True, sparse=True)
    try:
        await db["force_channels"].drop_index("channel_username_1")
    except Exception:
        pass
    await db["force_channels"].create_index("channel_username", unique=True, sparse=True)
    await db["bot_images"].create_index("screen_name", unique=True)
    await db["settings"].create_index("key", unique=True)
    await db["last_redeem"].create_index("user_id", unique=True)
    await db["bot_emojis"].create_index("position", unique=True)
    await db["admin_logs"].create_index("created_at")

    for key, value in DEFAULT_SETTINGS.items():
        await db["settings"].update_one(
            {"key": key},
            {"$setOnInsert": {"key": key, "value": value}},
            upsert=True,
        )


# ═══════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════

async def get_setting(key: str, default: str = "") -> str:
    doc = await col("settings").find_one({"key": key})
    return doc["value"] if doc else default


async def set_setting(key: str, value: str) -> None:
    await col("settings").update_one(
        {"key": key},
        {"$set": {"value": value}},
        upsert=True,
    )


async def get_all_settings() -> dict[str, str]:
    cursor = col("settings").find({})
    return {doc["key"]: doc["value"] async for doc in cursor}


# ═══════════════════════════════════════
# MAINTENANCE MODE
# ═══════════════════════════════════════

async def is_maintenance() -> bool:
    val = await get_setting("maintenance_mode", "0")
    return val == "1"


async def set_maintenance(enabled: bool) -> None:
    await set_setting("maintenance_mode", "1" if enabled else "0")


# ═══════════════════════════════════════
# USER HELPERS
# ═══════════════════════════════════════

def _gen_referral_code(length: int = 8) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def _user_doc_to_row(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    doc.setdefault("is_verified",  0)
    doc.setdefault("is_banned",    0)
    doc.setdefault("points",       0.0)
    doc.setdefault("referral_code", "")
    doc.setdefault("referred_by",   None)
    return doc


async def get_user(telegram_id: int) -> Optional[dict]:
    doc = await col("users").find_one({"telegram_id": telegram_id})
    return _user_doc_to_row(doc)


async def get_user_by_username(username: str) -> Optional[dict]:
    doc = await col("users").find_one({"username": username.lstrip("@")})
    return _user_doc_to_row(doc)


async def create_user(
    telegram_id: int, username: str, full_name: str,
    referred_by: Optional[int] = None,
) -> Optional[dict]:
    code = _gen_referral_code()
    doc  = {
        "telegram_id":   telegram_id,
        "username":      username or "",
        "full_name":     full_name or "Unknown",
        "is_verified":   0,
        "is_banned":     0,
        "points":        0.0,
        "referral_code": code,
        "referred_by":   referred_by,
        "created_at":    datetime.now(timezone.utc),
    }
    try:
        await col("users").insert_one(doc)
    except Exception:
        pass
    return _user_doc_to_row(await col("users").find_one({"telegram_id": telegram_id}))


async def update_user_info(telegram_id: int, username: str, full_name: str) -> None:
    await col("users").update_one(
        {"telegram_id": telegram_id},
        {"$set": {"username": username or "", "full_name": full_name or "Unknown"}},
    )


async def set_user_verified(telegram_id: int, verified: int) -> None:
    await col("users").update_one(
        {"telegram_id": telegram_id},
        {"$set": {"is_verified": verified}},
    )


async def set_user_banned(telegram_id: int, banned: int) -> None:
    await col("users").update_one(
        {"telegram_id": telegram_id},
        {"$set": {"is_banned": banned}},
    )


async def add_points(telegram_id: int, amount: float) -> None:
    await col("users").update_one(
        {"telegram_id": telegram_id},
        {"$inc": {"points": amount}},
    )


async def deduct_points(telegram_id: int, amount: float) -> None:
    await col("users").update_one(
        {"telegram_id": telegram_id},
        {"$inc": {"points": -amount}},
    )


async def get_all_users() -> list[dict]:
    docs = await col("users").find({}).to_list(length=None)
    return [_user_doc_to_row(d) for d in docs]


async def get_user_count() -> int:
    return await col("users").count_documents({})


async def get_verified_user_count() -> int:
    return await col("users").count_documents({"is_verified": 1})


async def get_today_user_count() -> int:
    """Count users who joined today (UTC)."""
    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return await col("users").count_documents({"created_at": {"$gte": start_of_day}})


async def get_total_points_in_circulation() -> float:
    """Sum of all points held by all users."""
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$points"}}}]
    result   = await col("users").aggregate(pipeline).to_list(length=1)
    return round(result[0]["total"], 2) if result else 0.0


async def get_top_referrers(limit: int = 10) -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$referrer_id", "ref_count": {"$sum": 1}}},
        {"$sort": {"ref_count": -1}},
        {"$limit": limit},
    ]
    rows   = await col("referrals").aggregate(pipeline).to_list(length=None)
    result = []
    for row in rows:
        uid  = row["_id"]
        user = await get_user(uid)
        if user:
            result.append({
                "telegram_id": uid,
                "full_name":   user["full_name"],
                "username":    user["username"],
                "ref_count":   row["ref_count"],
            })
    return result


# ═══════════════════════════════════════
# REFERRALS
# ═══════════════════════════════════════

async def add_referral(referrer_id: int, referred_id: int) -> bool:
    """Add referral relationship. Returns False if already exists (idempotent fraud guard)."""
    try:
        # Guard: check that this referred_id hasn't already been credited to ANY referrer
        existing = await col("referrals").find_one({"referred_id": referred_id})
        if existing:
            return False
        await col("referrals").insert_one({
            "referrer_id": referrer_id,
            "referred_id": referred_id,
            "created_at":  datetime.now(timezone.utc),
        })
        return True
    except Exception:
        return False


async def get_referral_count(referrer_id: int) -> int:
    return await col("referrals").count_documents({"referrer_id": referrer_id})


async def get_referrals(referrer_id: int) -> list[dict]:
    docs   = await col("referrals").find({"referrer_id": referrer_id}).to_list(length=None)
    result = []
    for doc in docs:
        user = await get_user(doc["referred_id"])
        if user:
            result.append(user)
    return result


async def get_user_by_referral_code(code: str) -> Optional[dict]:
    doc = await col("users").find_one({"referral_code": code})
    return _user_doc_to_row(doc)


# ═══════════════════════════════════════
# ADMINS
# ═══════════════════════════════════════

async def is_admin(user_id: int, master_admin_id: int) -> bool:
    if user_id == master_admin_id:
        return True
    doc = await col("admins").find_one({"user_id": user_id})
    return doc is not None


async def add_admin(user_id: int, username: str = "", role: str = "admin") -> None:
    await col("admins").update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "username": username, "role": role}},
        upsert=True,
    )


async def remove_admin(user_id: int) -> None:
    await col("admins").delete_one({"user_id": user_id})


async def get_all_admins() -> list[dict]:
    docs = await col("admins").find({}).to_list(length=None)
    return [_norm(d) for d in docs]


# ═══════════════════════════════════════
# FORCE CHANNELS
# ═══════════════════════════════════════

async def get_all_channels() -> list[dict]:
    docs = await col("force_channels").find({}).to_list(length=None)
    return [_norm(d) for d in docs]


async def add_channel(
    channel_id: Optional[int],
    channel_username: str,
    display_name: str,
    channel_link: str,
) -> None:
    doc = {
        "channel_username": channel_username.lstrip("@") if channel_username else "",
        "display_name":     display_name,
        "channel_link":     channel_link,
        "added_at":         datetime.now(timezone.utc),
    }
    if channel_id is not None:
        doc["channel_id"] = channel_id

    if channel_id is not None:
        await col("force_channels").update_one(
            {"channel_id": channel_id},
            {"$set": doc},
            upsert=True,
        )
    elif channel_username:
        await col("force_channels").update_one(
            {"channel_username": channel_username.lstrip("@")},
            {"$set": doc},
            upsert=True,
        )
    else:
        await col("force_channels").insert_one(doc)


async def remove_channel(channel_id: int) -> bool:
    result = await col("force_channels").delete_one({"channel_id": channel_id})
    return result.deleted_count > 0


async def remove_channel_by_username(username: str) -> bool:
    result = await col("force_channels").delete_one(
        {"channel_username": username.lstrip("@")}
    )
    return result.deleted_count > 0


async def clear_all_channels() -> int:
    result = await col("force_channels").delete_many({})
    return result.deleted_count


# ═══════════════════════════════════════
# ORDERS
# ═══════════════════════════════════════

async def create_order(
    user_id: int,
    service: str,
    quantity: int,
    instagram_link: str,
    points_spent: float,
    jap_order_id: str = "",
) -> str:
    from bson import ObjectId
    oid = ObjectId()
    await col("orders").insert_one({
        "_id":            oid,
        "user_id":        user_id,
        "service":        service,
        "quantity":       quantity,
        "instagram_link": instagram_link,
        "points_spent":   points_spent,
        "jap_order_id":   jap_order_id,
        "status":         "pending",
        "refunded":       False,
        "created_at":     datetime.now(timezone.utc),
    })
    return str(oid)


async def get_order(order_id: str) -> Optional[dict]:
    from bson import ObjectId
    try:
        doc = await col("orders").find_one({"_id": ObjectId(order_id)})
    except Exception:
        doc = await col("orders").find_one({"jap_order_id": order_id})
    return _norm(doc)


async def update_order_status(order_id: str, status: str) -> None:
    from bson import ObjectId
    try:
        await col("orders").update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}},
        )
    except Exception:
        pass


async def mark_order_refunded(order_id: str) -> None:
    from bson import ObjectId
    try:
        await col("orders").update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"refunded": True}},
        )
    except Exception:
        pass


async def update_order_jap_id(order_id: str, jap_id: str) -> None:
    from bson import ObjectId
    try:
        await col("orders").update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"jap_order_id": jap_id}},
        )
    except Exception:
        pass


async def get_pending_orders() -> list[dict]:
    docs = await col("orders").find(
        {"status": {"$in": ["pending", "In progress", "processing"]}}
    ).to_list(length=None)
    return [_norm(d) for d in docs]


async def get_all_orders(limit: int = 100) -> list[dict]:
    docs = await (
        col("orders").find({}).sort("created_at", -1).limit(limit).to_list(length=None)
    )
    return [_norm(d) for d in docs]


async def has_recent_order(
    user_id: int, instagram_link: str, service: str, window_seconds: int
) -> bool:
    """Duplicate order guard: True if same user/link/service order exists within window."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    doc    = await col("orders").find_one({
        "user_id":        user_id,
        "instagram_link": instagram_link,
        "service":        service,
        "created_at":     {"$gte": cutoff},
    })
    return doc is not None


async def get_orders_count_by_status() -> dict[str, int]:
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    rows     = await col("orders").aggregate(pipeline).to_list(length=None)
    return {row["_id"]: row["count"] for row in rows}


# ═══════════════════════════════════════
# GIFT CODES
# ═══════════════════════════════════════

async def create_gift_code(
    code: str, name: str, points: float,
    max_uses: int = 1, expires_at: Optional[datetime] = None,
) -> None:
    await col("gift_codes").insert_one({
        "code":       code,
        "name":       name,
        "points":     points,
        "max_uses":   max_uses,
        "used_count": 0,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
    })


async def get_gift_code(code: str) -> Optional[dict]:
    doc = await col("gift_codes").find_one({"code": code})
    return _norm(doc)


async def get_all_gift_codes() -> list[dict]:
    docs = await col("gift_codes").find({}).to_list(length=None)
    return [_norm(d) for d in docs]


async def increment_code_use(code: str) -> None:
    await col("gift_codes").update_one(
        {"code": code},
        {"$inc": {"used_count": 1}},
    )


async def delete_gift_code(code: str) -> None:
    await col("gift_codes").delete_one({"code": code})


async def has_redeemed(code: str, user_id: int) -> bool:
    doc = await col("code_redemptions").find_one({"code": code, "user_id": user_id})
    return doc is not None


async def add_redemption(code: str, user_id: int) -> None:
    try:
        await col("code_redemptions").insert_one({
            "code":        code,
            "user_id":     user_id,
            "redeemed_at": datetime.now(timezone.utc),
        })
    except Exception:
        pass


async def get_last_redeem_time(user_id: int) -> Optional[datetime]:
    doc = await col("last_redeem").find_one({"user_id": user_id})
    return doc["redeemed_at"] if doc else None


async def set_last_redeem_time(user_id: int) -> None:
    await col("last_redeem").update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "redeemed_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


# ═══════════════════════════════════════
# BOT IMAGES
# ═══════════════════════════════════════

async def get_image(screen_name: str) -> Optional[str]:
    doc = await col("bot_images").find_one({"screen_name": screen_name})
    return doc["file_id"] if doc else None


async def set_image(screen_name: str, file_id: str) -> None:
    await col("bot_images").update_one(
        {"screen_name": screen_name},
        {"$set": {"screen_name": screen_name, "file_id": file_id}},
        upsert=True,
    )


async def delete_image(screen_name: str) -> None:
    await col("bot_images").delete_one({"screen_name": screen_name})


async def get_all_images() -> dict[str, Optional[str]]:
    docs = await col("bot_images").find({}).to_list(length=None)
    return {d["screen_name"]: d.get("file_id") for d in docs}


# ═══════════════════════════════════════
# BOT EMOJIS
# ═══════════════════════════════════════

async def upsert_bot_emoji(
    position: int, emoji_id: str, fallback: str,
    description: str, placement: str, key_name: str,
) -> None:
    await col("bot_emojis").update_one(
        {"position": position},
        {"$set": {
            "position":    position,
            "emoji_id":    emoji_id,
            "fallback":    fallback,
            "description": description,
            "placement":   placement,
            "key_name":    key_name,
            "updated_at":  datetime.now(timezone.utc),
        }},
        upsert=True,
    )


async def get_all_bot_emojis() -> list[dict]:
    return await col("bot_emojis").find({}).sort("position", 1).to_list(length=None)


async def get_bot_emoji(position: int) -> Optional[dict]:
    return await col("bot_emojis").find_one({"position": position})


# ═══════════════════════════════════════
# ADMIN ACTION LOGS
# ═══════════════════════════════════════

async def log_admin_action(action: str, admin_id: int, detail: str = "") -> None:
    await col("admin_logs").insert_one({
        "action":    action,
        "admin_id":  admin_id,
        "detail":    detail,
        "created_at": datetime.now(timezone.utc),
    })


async def get_recent_admin_logs(limit: int = 50) -> list[dict]:
    docs = await (
        col("admin_logs")
        .find({})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(length=None)
    )
    return [_norm(d) for d in reversed(docs)]
