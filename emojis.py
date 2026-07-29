"""
emojis.py — Premium Telegram Animated Emoji System
Uses <tg-emoji emoji-id="..."> HTML tags for animated premium emojis.
Every emoji is contextually matched to its use case.
Run /add then /apply in the bot to update IDs from live messages.

IMPORTANT: <tg-emoji> only renders as animated emoji if the bot owner's
Telegram account has an active Premium subscription.  If not, set
PREMIUM_EMOJI_ENABLED = False in config.py — e() will then return plain
Unicode fallback characters only, guaranteeing all messages send correctly.
"""

from config import PREMIUM_EMOJI_ENABLED

# ═══════════════════════════════════════
# PREMIUM EMOJI DICT
# Format: key → (emoji_id, fallback_char)
# Emoji IDs must be Telegram's custom emoji sticker IDs.
# ═══════════════════════════════════════
PREMIUM: dict[str, tuple[str, str]] = {
    # ── Core status ────────────────────────────────────────────────
    # Format: key → (premium_emoji_id, plain_text_fallback)
    # Fallbacks are minimal text — normal Unicode emojis are intentionally removed.
    "welcome":      ("5345811932085510702", "~"),
    "check":        ("5895514131896733546", "+"),
    "warning":      ("5893163582194978381", "!"),
    "success":      ("5893081007153746175", "+"),
    "error":        ("5893442248263078309", "x"),
    "loading":      ("6098365712164724805", ".."),
    "pending":      ("5444987348334965906", "~"),
    # ── Admin / roles ──────────────────────────────────────────────
    "crown":        ("5893034681636491040", "*"),
    "key":          ("6098239122298644900", "#"),
    "admin":        ("5447224884562263112", "#"),
    "admins":       ("5445373981290952548", "#"),
    "ban":          ("6100331522991072240", "x"),
    "banned":       ("6100331522991072240", "x"),
    "captcha":      ("5445163158526261598", "#"),
    # ── Bot panels ─────────────────────────────────────────────────
    "panel":        ("5445326466067754897", ">"),
    "settings":     ("5904238507555033712", ">"),
    "system":       ("5445408306669582934", ">"),
    "broadcast":    ("5447651546613449378", ">"),
    "botstats":     ("6321106487116569877", ">"),
    "stats":        ("5893224751119208859", ">"),
    # ── User / identity ────────────────────────────────────────────
    "user":         ("5902016123972358349", "@"),
    "id":           ("5893100690988863311", "#"),
    "verified":     ("6098076995873153414", "+"),
    # ── Money / points ─────────────────────────────────────────────
    "balance":      ("5895652322469482989", "$"),
    "points":       ("5893365724830765382", "*"),
    "money":        ("6097918275356736308", "$"),
    "earn":         ("6098431695747291957", "+"),
    "bonus":        ("6098350400606314376", "+"),
    "withdraw":     ("6201651566735269334", "$"),
    "diamond":      ("5893185207355315979", "*"),
    "gift":         ("5893321843149902412", "+"),
    # ── Social / Instagram ─────────────────────────────────────────
    "instagram":    ("5219899949281453881", "@"),
    "followers":    ("5895444149699612825", "+"),
    "likes":        ("5893494861612455015", "+"),
    "views":        ("5893162100431261050", "+"),
    "comments":     ("5893402730268987918", "+"),
    "link":         ("5222148368955877900", ">"),
    "channel":      ("5895213106228891182", ">"),
    "proofs":       ("5444883062234053429", ">"),
    # ── Navigation ─────────────────────────────────────────────────
    "back":         ("5893406892092297627", "<"),
    "refresh":      ("5902002809573740949", "~"),
    "close":        ("6203901695806677581", "x"),
    "cancel":       ("6203901695806677581", "x"),
    "plus":         ("5904692292324692386", "+"),
    "remove":       ("6089364701957853465", "-"),
    "send":         ("5893450623449305489", ">"),
    "menu":         ("6098400471335055043", "="),
    # ── Misc / decorative ──────────────────────────────────────────
    "fire":         ("5895440460322706085", "*"),
    "star":         ("6098412462883741731", "*"),
    "sparkle":      ("6100335212367978410", "*"),
    "rocket":       ("5319250759110374827", "^"),
    "trophy":       ("5893048571560726748", "*"),
    "top":          ("5893203503915996356", "^"),
    "pin":          ("6098030013225901224", ">"),
    "tip":          ("5219672809936006424", "i"),
    "magic":        ("6098109126523493765", "*"),
    "rainbow":      ("5258079378159453410", "~"),
    "moon":         ("5316538964004321334", "~"),
    "sun":          ("5316711376876485361", "*"),
    "butterfly":    ("5316881354502192070", "~"),
    "flower":       ("5316561083085895267", "*"),
    "ribbon":       ("5319211649138177073", "*"),
    "brain":        ("6098325597170180563", "~"),
    "promo":        ("5222108309795908493", "*"),
    "live":         ("5219943216781995020", "."),
    "premium":      ("5220046725493828505", "*"),
    "medal":        ("5220197908342648622", "*"),
    "music":        ("5454386656628991407", "~"),
    "paint":        ("5454360341364363439", "~"),
    "event":        ("5445350109862720603", "*"),
    "divider":      ("5447506720316225765", "-"),
    "stock":        ("5444862970377040012", ">"),
    "refer":        ("5893072412924187198", ">"),
    "refer_menu":   ("5445140257760639304", "+"),
    "balance_menu": ("5445364025556759279", "$"),
    "support":      ("6242282747629413332", "?"),
    "ice":          ("5454249887690415056", "*"),
    "key_code":     ("6098239122298644900", "#"),
    # ── Super Control (master admin) ───────────────────────────────
    "super":        ("5893034681636491040", "*"),
    "logs":         ("5445408306669582934", ">"),
    "reboot":       ("5902002809573740949", "~"),
    "token":        ("6098239122298644900", "#"),
    "github":       ("5893224751119208859", ">"),
    # ── Maintenance ────────────────────────────────────────────────
    "maintenance":  ("5893163582194978381", "!"),
    "wrench":       ("5893163582194978381", "!"),
    # ── Scope / posting type ───────────────────────────────────────
    "single_post":  ("5893494861612455015", ">"),
    "all_posts":    ("5895444149699612825", ">"),
    # ── Misc aliases ───────────────────────────────────────────────
    "check_join":   ("6098076995873153414", "+"),
    "panel_menu":   ("5445326466067754897", ">"),
}

# Runtime override — loaded from DB at startup
_OVERRIDE: dict[str, tuple[str, str]] = {}


def update_override(new_dict: dict) -> None:
    """Update emoji overrides at runtime (called from DB emoji store)."""
    global _OVERRIDE
    processed: dict[str, tuple[str, str]] = {}
    for k, v in new_dict.items():
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            processed[k] = (str(v[0]), str(v[1]))
        elif isinstance(v, str) and v:
            fb = PREMIUM.get(k, ("", "•"))[1]
            processed[k] = (v, fb)
    _OVERRIDE = processed


def e(name: str, fallback: str = None) -> str:
    """
    Return an animated premium emoji HTML tag.
    Falls back to the character in PREMIUM[name] if no override.
    When PREMIUM_EMOJI_ENABLED is False, returns only the plain Unicode
    fallback character — this guarantees messages send regardless of
    whether the bot owner has a Telegram Premium subscription.
    Usage: e('crown')  or  e('crown', '👑')
    """
    pair = _OVERRIDE.get(name) or PREMIUM.get(name)
    if pair:
        if isinstance(pair, tuple):
            eid, fb = pair
        else:
            eid, fb = str(pair), (fallback or "•")
        display = fallback if fallback is not None else fb
        # Only use <tg-emoji> wrapper when Premium is enabled AND we have an ID
        if eid and PREMIUM_EMOJI_ENABLED:
            return f'<tg-emoji emoji-id="{eid}">{display}</tg-emoji>'
        return display
    return fallback or "•"


def divider() -> str:
    """Styled section divider for messages using premium animated emoji."""
    sep = e('instagram')
    return f"\n{sep} {'─' * 18} {sep}\n"


def header(title: str, icon: str = "crown", icon_fb: str = "👑") -> str:
    """Bold header with premium emoji."""
    return f"{e(icon, icon_fb)} <b>{title}</b>"


def status_line(label: str, value: str, icon: str, icon_fb: str = "•") -> str:
    """Formatted status line."""
    return f"{e(icon, icon_fb)} <b>{label}:</b> {value}"
