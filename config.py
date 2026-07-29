"""
config.py — Central configuration for Instagram Free Followers Bot
All settings are managed here and in the admin panel.
No environment variables required — configure everything in this file or via bot.
"""

# ═══════════════════════════════════════
# BOT CREDENTIALS  ← change these
# ═══════════════════════════════════════
BOT_TOKEN: str = "8469087220:AAH_zKq35ak94JwSFNnCeCMABGzi5gCTh4k"
BOT_NAME: str  = "Instagram Bot"
BOT_USERNAME: str = ""  # auto-set on startup

# ═══════════════════════════════════════
# ADMIN CONFIGURATION  ← master admin never changes
# ═══════════════════════════════════════
MASTER_ADMIN_ID: int  = 8264404281   # @iam_esh — immutable
MASTER_ADMIN_USERNAME: str = "iam_esh"

# General support contact (your client)
GENERAL_SUPPORT_USERNAME: str = "notnow1122"

# Developer contact
DEVELOPER_USERNAME: str = "@iam_esh"

# ═══════════════════════════════════════
# JAP API CONFIGURATION
# ═══════════════════════════════════════
JAP_API_KEY: str  = "TEST_API_KEY_12345"   # override from admin panel
JAP_BASE_URL: str = "https://justanotherpanel.in/api/v2"
JAP_TIMEOUT: int  = 30

# ═══════════════════════════════════════
# DATABASE (MongoDB Atlas)
# ═══════════════════════════════════════
MONGODB_URI: str = (
    "mongodb+srv://singhyashraj:leechbotxesh@cluster0.i1ruod.mongodb.net/"
    "?appName=Cluster0"
)

# ═══════════════════════════════════════
# GITHUB REPOSITORY  (for Super Control "Check Latest Push")
# ═══════════════════════════════════════
GITHUB_REPO_URL: str = "https://github.com/esh-bc/instagram"

# ═══════════════════════════════════════
# PREMIUM EMOJI FEATURE FLAG
# Set to False if the bot owner does NOT have an active Telegram Premium
# subscription — this makes e() return plain Unicode fallback chars only,
# guaranteeing every message sends successfully.  Flip to True once Premium
# is active and you want animated custom emoji in messages.
# ═══════════════════════════════════════
PREMIUM_EMOJI_ENABLED: bool = True

# ═══════════════════════════════════════
# DEFAULT SETTINGS  (seeded to DB on first run, editable via admin panel)
# ═══════════════════════════════════════
DEFAULT_SETTINGS: dict = {
    # Points & ratios
    "min_withdraw_points":    "10",
    "points_per_refer":       "5",
    "followers_points":       "10",
    "followers_amount":       "100",
    "likes_points":           "5",
    "likes_amount":           "50",
    "views_points":           "3",
    "views_amount":           "100",
    "comments_points":        "15",
    "comments_amount":        "10",
    # JAP service IDs
    "jap_followers_service_id":  "",
    "jap_likes_service_id":      "",
    "jap_views_service_id":      "",
    "jap_comments_service_id":   "",
    # Service scope: "single" = specific post/reel, "all" = all posts on account
    "jap_likes_service_scope":    "single",
    "jap_comments_service_scope": "single",
    # Bot feature flags
    "captcha_enabled":  "0",
    "force_reverify":   "0",
    "maintenance_mode": "0",   # "1" = maintenance ON
    # Proof channel
    "proofs_channel":          "@proofs_channel",
    "proof_channel_id":        "",
    "proof_channel_link":      "",
    "proof_channel_username":  "",
    # JAP API credentials (hot-reload without restart)
    "jap_api_key": "",
    "jap_api_url": "",
    # Custom messages
    "promo_text":     "",
    "promo_entities": "",
    "promo_mode":     "always",
    "menu_text":      "",
    "menu_entities":  "",
    # Emoji overrides
    "premium_emojis": "",
}

# ═══════════════════════════════════════
# BACKGROUND TASK INTERVALS
# ═══════════════════════════════════════
ORDER_CHECK_INTERVAL: int = 300   # 5 minutes

# ═══════════════════════════════════════
# GIFT CODE SETTINGS
# ═══════════════════════════════════════
GIFT_CODE_COOLDOWN: int = 600   # 10 minutes

# ═══════════════════════════════════════
# BROADCAST SETTINGS
# ═══════════════════════════════════════
BROADCAST_DELAY: float = 0.05

# ═══════════════════════════════════════
# LOG BUFFER SIZE  (for Super Control live logs)
# ═══════════════════════════════════════
LOG_BUFFER_SIZE: int = 100

# ═══════════════════════════════════════
# RATE LIMITING — withdraw link input
# Max submissions of the same Instagram link per user within this window (seconds).
# ═══════════════════════════════════════
LINK_RATE_WINDOW: int   = 60   # seconds
LINK_RATE_MAX:    int   = 3    # max attempts per window

# ═══════════════════════════════════════
# DUPLICATE ORDER GUARD
# Block placing the same (user, link, service) combo within this window.
# ═══════════════════════════════════════
DUPLICATE_ORDER_WINDOW: int = 300   # 5 minutes

# ═══════════════════════════════════════
# SCREEN NAMES  (for bot_images table)
# ═══════════════════════════════════════
SCREENS = [
    "promo", "welcome", "main", "balance", "refer",
    "withdraw", "giftcode", "stock", "support", "proofs",
]
