"""
Tovest Tracking Bot v3
----------------------
Matches incoming ChatJoinRequests against 3 pre-existing invite links for the
Trading Signal group to determine traffic source (vietnam / indonesia / global).

Flow:
  1. User clicks one of the 3 known invite links and submits a join request.
  2. Bot receives ChatJoinRequest, reads the invite_link field.
  3. Bot matches the link against the configured INVITE_LINK_* env vars.
  4. Bot auto-approves the join request.
  5. Bot sends a localised welcome DM with the corresponding tracked registration link.
  6. Event is logged to SQLite (user_id, username, source, timestamp).

Admin commands: /start, /stats
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ChatJoinRequestHandler,
    CommandHandler,
    ContextTypes,
)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

BASE_DIR = Path(__file__).parent
LOG_DIR  = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
DB_PATH  = Path(os.getenv("DB_PATH", str(BASE_DIR / "tracking.db")))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("tovest_bot")

# ---------------------------------------------------------------------------
# Welcome message templates
# ---------------------------------------------------------------------------

WELCOME_TEMPLATES: dict[str, dict] = {
    "vietnam": {
        "text": (
            "Chào mừng bạn đã tham gia cộng đồng Tovest Trading Signal\\! 🎉\n\n"
            "Tovest là nền tảng giao dịch cổ phiếu token hóa với *0 hoa hồng*, "
            "hỗ trợ tài khoản demo miễn phí để bạn luyện tập trước khi giao dịch thật\\.\n\n"
            "👉 Đăng ký ngay để bắt đầu hành trình đầu tư của bạn:"
        ),
        "button_label": "Đăng ký Tovest",
    },
    "indonesia": {
        "text": (
            "Selamat datang di komunitas Tovest Trading Signal\\! 🎉\n\n"
            "Tovest adalah platform trading saham tokenisasi dengan *0 komisi*, "
            "lengkap dengan akun demo gratis untuk berlatih sebelum trading sungguhan\\.\n\n"
            "👉 Daftar sekarang dan mulai perjalanan investasimu:"
        ),
        "button_label": "Daftar Tovest",
    },
    "global": {
        "text": (
            "Welcome to the Tovest Trading Signal community\\! 🎉\n\n"
            "Tovest is a tokenized stock trading platform with *zero commission* "
            "and a free demo account so you can practice risk\\-free before going live\\.\n\n"
            "👉 Sign up now and start your investment journey:"
        ),
        "button_label": "Sign Up for Tovest",
    },
}

# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------

def load_invite_link_map() -> dict[str, str]:
    """
    Returns {invite_link_url: source_name} built from env vars.

    INVITE_LINK_VN    → "vietnam"
    INVITE_LINK_INDO  → "indonesia"
    INVITE_LINK_GLOBAL → "global"
    """
    mapping: dict[str, str] = {}
    pairs = [
        ("INVITE_LINK_VN",     "vietnam"),
        ("INVITE_LINK_INDO",   "indonesia"),
        ("INVITE_LINK_GLOBAL", "global"),
    ]
    for env_key, source in pairs:
        url = os.getenv(env_key, "").strip()
        if url:
            mapping[url] = source
        else:
            logger.warning("Missing env var %s — source '%s' will not be tracked.", env_key, source)
    return mapping


def load_tracked_url_map() -> dict[str, str]:
    """
    Returns {source_name: tracked_registration_url} built from env vars.
    """
    return {
        "vietnam":   os.getenv("LINK_VIETNAM",   ""),
        "indonesia": os.getenv("LINK_INDONESIA", ""),
        "global":    os.getenv("LINK_GLOBAL",    ""),
    }


def load_admin_ids() -> set[int]:
    raw = os.getenv("ADMIN_IDS", "")
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS join_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                username     TEXT,
                full_name    TEXT,
                source       TEXT NOT NULL,
                invite_link  TEXT,
                tracked_url  TEXT,
                approved_at  TEXT NOT NULL
            )
            """
        )
        conn.commit()
    logger.info("Database initialised at %s", DB_PATH)


def log_join(
    user_id: int,
    username: str | None,
    full_name: str,
    source: str,
    invite_link: str | None,
    tracked_url: str | None,
) -> None:
    approved_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO join_log
                (user_id, username, full_name, source, invite_link, tracked_url, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, full_name, source, invite_link, tracked_url, approved_at),
        )
        conn.commit()
    logger.info(
        "Logged join | user_id=%s username=%s source=%s", user_id, username, source
    )


def get_stats() -> list[tuple[str, int]]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT source, COUNT(*) FROM join_log GROUP BY source ORDER BY COUNT(*) DESC"
        ).fetchall()


def get_recent(limit: int = 5) -> list[tuple]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            """
            SELECT approved_at, user_id, username, full_name, source
            FROM join_log ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()


def get_total() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        (total,) = conn.execute("SELECT COUNT(*) FROM join_log").fetchone()
    return total

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Fired when a user submits a join request.
    Matches invite link → determines source → approves → sends welcome DM → logs.
    """
    req = update.chat_join_request
    if req is None:
        return

    user = req.from_user

    # Determine which invite link was used
    used_link = req.invite_link.invite_link if req.invite_link else None

    invite_link_map: dict[str, str] = context.bot_data.get("invite_link_map", {})
    tracked_url_map: dict[str, str] = context.bot_data.get("tracked_url_map", {})

    source = invite_link_map.get(used_link) if used_link else None

    if source is None:
        logger.info(
            "Join request from user %s via unrecognised link '%s' — marking as 'unknown'.",
            user.id, used_link,
        )
        source = "unknown"

    # Auto-approve the join request
    try:
        await req.approve()
        logger.info("Approved join request | user_id=%s source=%s", user.id, source)
    except TelegramError as exc:
        logger.error("Failed to approve join request for user %s: %s", user.id, exc)
        return

    # Send welcome DM (only for known sources)
    tracked_url = tracked_url_map.get(source) if source != "unknown" else None
    if source != "unknown" and tracked_url:
        template = WELCOME_TEMPLATES[source]
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(template["button_label"], url=tracked_url)]]
        )
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=template["text"],
                parse_mode="MarkdownV2",
                reply_markup=keyboard,
            )
            logger.info("Sent welcome DM | user_id=%s source=%s", user.id, source)
        except TelegramError as exc:
            # User may have blocked the bot or never started a DM — not a fatal error
            logger.warning("Could not send welcome DM to user %s: %s", user.id, exc)

    # Log the event regardless of DM success
    log_join(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name or user.username or str(user.id),
        source=source,
        invite_link=used_link,
        tracked_url=tracked_url,
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Hi! I'm the Tovest Trading Signal bot.\n\n"
        "I automatically approve join requests and send new members a personalised "
        "registration link based on which invite link they used.\n\n"
        "Admins can use /stats to view tracking data."
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only: show join stats per source."""
    if not _is_admin(update, context):
        await update.message.reply_text("⛔ You are not authorised to use this command.")
        return

    rows   = get_stats()
    total  = get_total()
    recent = get_recent(5)

    source_labels = {
        "vietnam":   "🇻🇳 Vietnam",
        "indonesia": "🇮🇩 Indonesia",
        "global":    "🌐 Global",
        "unknown":   "❓ Unknown",
    }

    lines = ["📊 *Tovest Tracking Bot — Stats*\n"]
    lines.append(f"*Total approved joins:* {total}\n")

    if rows:
        lines.append("*By source:*")
        for source, cnt in rows:
            label = source_labels.get(source, source)
            lines.append(f"  • {label}: {cnt}")
    else:
        lines.append("No data yet.")

    if recent:
        lines.append("\n*Last 5 joins:*")
        for approved_at, uid, uname, fname, src in recent:
            dt      = approved_at[:19].replace("T", " ")
            display = f"@{uname}" if uname else (fname or str(uid))
            label   = source_labels.get(src, src)
            lines.append(f"  `{dt}` — {display} → {label}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    admin_ids: set[int] = context.bot_data.get("admin_ids", set())
    user = update.effective_user
    return bool(user and user.id in admin_ids)


async def post_init(application: Application) -> None:
    """Runs after the Application is fully initialised."""
    invite_link_map = load_invite_link_map()
    tracked_url_map = load_tracked_url_map()
    admin_ids       = load_admin_ids()

    application.bot_data["invite_link_map"] = invite_link_map
    application.bot_data["tracked_url_map"] = tracked_url_map
    application.bot_data["admin_ids"]       = admin_ids

    logger.info(
        "Bot ready | tracked invite links=%d | admins=%d",
        len(invite_link_map), len(admin_ids),
    )
    for link, source in invite_link_map.items():
        logger.info("  %s → %s", link, source)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")

    init_db()

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stats", stats_command))

    logger.info("Starting bot (polling)…")
    app.run_polling(allowed_updates=["chat_join_request", "message"])


if __name__ == "__main__":
    main()
