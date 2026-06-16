"""
Tovest Tracking Bot
-------------------
Sends tracked registration links to new members joining configured Telegram groups.
Each group has its own full tracked URL defined via environment variables.
Logs each welcome event and provides an admin /stats command.
"""

import os
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ChatMemberHandler,
    ContextTypes,
)
from telegram.constants import ChatMemberStatus

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "tracking.db")))

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
# Configuration helpers
# ---------------------------------------------------------------------------

def load_group_config() -> dict[str, dict]:
    """
    Build the group config from env vars.

    Returns a dict keyed by chat_id string:
        {
            "<chat_id>": {
                "source":      "global" | "vietnam" | "indonesia",
                "tracked_url": "https://...",
            },
            ...
        }
    """
    groups = {
        "global":    {"env_id": "GROUP_GLOBAL",    "env_link": "LINK_GLOBAL"},
        "vietnam":   {"env_id": "GROUP_VIETNAM",   "env_link": "LINK_VIETNAM"},
        "indonesia": {"env_id": "GROUP_INDONESIA", "env_link": "LINK_INDONESIA"},
    }

    config: dict[str, dict] = {}
    for source, keys in groups.items():
        chat_id = os.getenv(keys["env_id"])
        link    = os.getenv(keys["env_link"])
        if chat_id and link:
            config[str(chat_id)] = {"source": source, "tracked_url": link}
        else:
            logger.warning(
                "Missing env vars for source '%s': %s=%s, %s=%s",
                source, keys["env_id"], chat_id, keys["env_link"], link,
            )

    if config:
        logger.info("Loaded group config: %s", {k: v["source"] for k, v in config.items()})
    else:
        logger.warning("No group config loaded. Check GROUP_GLOBAL/VIETNAM/INDONESIA and LINK_* vars.")
    return config


def load_admin_ids() -> set[int]:
    """Parse comma-separated ADMIN_IDS env var into a set of integers."""
    raw = os.getenv("ADMIN_IDS", "")
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


# ---------------------------------------------------------------------------
# Welcome message templates  (3 groups, 3 languages)
# ---------------------------------------------------------------------------

WELCOME_TEMPLATES: dict[str, dict] = {
    "vietnam": {
        "text": (
            "Chào mừng {name} đến với cộng đồng Tovest Vietnam! 🎉\n\n"
            "Tovest là nền tảng giao dịch cổ phiếu token hóa với *0 hoa hồng*, "
            "hỗ trợ tài khoản demo miễn phí để bạn luyện tập trước khi giao dịch thật.\n\n"
            "👉 Đăng ký ngay để bắt đầu hành trình đầu tư của bạn:"
        ),
        "button_label": "Đăng ký Tovest",
    },
    "indonesia": {
        "text": (
            "Selamat datang {name} di komunitas Tovest Indonesia! 🎉\n\n"
            "Tovest adalah platform trading saham tokenisasi dengan *0 komisi*, "
            "lengkap dengan akun demo gratis untuk berlatih sebelum trading sungguhan.\n\n"
            "👉 Daftar sekarang dan mulai perjalanan investasimu:"
        ),
        "button_label": "Daftar Tovest",
    },
    "global": {
        "text": (
            "Welcome {name} to the Tovest Global community! 🎉\n\n"
            "Tovest is a tokenized stock trading platform with *zero commission* "
            "and a free demo account so you can practice risk-free before going live.\n\n"
            "👉 Sign up now and start your investment journey:"
        ),
        "button_label": "Sign Up for Tovest",
    },
}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS welcome_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                username    TEXT,
                full_name   TEXT,
                chat_id     INTEGER NOT NULL,
                source      TEXT NOT NULL,
                tracked_url TEXT NOT NULL,
                sent_at     TEXT NOT NULL
            )
            """
        )
        conn.commit()
    logger.info("Database initialised at %s", DB_PATH)


def log_welcome(
    user_id: int,
    username: str | None,
    full_name: str,
    chat_id: int,
    source: str,
    tracked_url: str,
) -> None:
    sent_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO welcome_log
                (user_id, username, full_name, chat_id, source, tracked_url, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, full_name, chat_id, source, tracked_url, sent_at),
        )
        conn.commit()
    logger.info(
        "Logged welcome | user_id=%s username=%s source=%s", user_id, username, source
    )


def get_stats() -> list[tuple[str, int]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM welcome_log GROUP BY source ORDER BY cnt DESC"
        ).fetchall()
    return rows


def get_recent(limit: int = 10) -> list[tuple]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT sent_at, user_id, username, full_name, source
            FROM welcome_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows


def get_total() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        (total,) = conn.execute("SELECT COUNT(*) FROM welcome_log").fetchone()
    return total


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Triggered when a chat member status changes."""
    result = update.chat_member
    if result is None:
        return

    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status

    joined = new_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    ) and old_status in (
        ChatMemberStatus.LEFT,
        ChatMemberStatus.BANNED,
        ChatMemberStatus.RESTRICTED,
    )

    if not joined:
        return

    user = result.new_chat_member.user
    if user.is_bot:
        return

    chat_id_str = str(result.chat.id)
    group_config: dict[str, dict] = context.bot_data.get("group_config", {})
    group_info = group_config.get(chat_id_str)

    if group_info is None:
        logger.debug(
            "New member in untracked chat %s (user %s) — skipping.", chat_id_str, user.id
        )
        return

    source      = group_info["source"]
    tracked_url = group_info["tracked_url"]
    full_name   = user.full_name or user.username or "there"
    template    = WELCOME_TEMPLATES[source]

    text     = template["text"].format(name=full_name)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(template["button_label"], url=tracked_url)]]
    )

    try:
        await context.bot.send_message(
            chat_id=result.chat.id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        log_welcome(
            user_id=user.id,
            username=user.username,
            full_name=full_name,
            chat_id=result.chat.id,
            source=source,
            tracked_url=tracked_url,
        )
    except Exception as exc:
        logger.error(
            "Failed to send welcome to user %s in chat %s: %s", user.id, chat_id_str, exc
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin-only /stats command."""
    admin_ids: set[int] = context.bot_data.get("admin_ids", set())
    user = update.effective_user

    if not user or user.id not in admin_ids:
        await update.message.reply_text("⛔ You are not authorised to use this command.")
        return

    rows   = get_stats()
    total  = get_total()
    recent = get_recent(5)

    lines = ["📊 *Tovest Tracking Bot — Stats*\n"]
    lines.append(f"*Total welcome messages sent:* {total}\n")

    if rows:
        lines.append("*By source:*")
        for source, cnt in rows:
            lines.append(f"  • `{source}`: {cnt}")
    else:
        lines.append("No data yet.")

    if recent:
        lines.append("\n*Last 5 events:*")
        for sent_at, uid, uname, fname, src in recent:
            dt      = sent_at[:19].replace("T", " ")
            display = uname or fname or str(uid)
            lines.append(f"  `{dt}` — @{display} → `{src}`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Basic /start response for direct messages."""
    await update.message.reply_text(
        "👋 I'm the Tovest welcome bot. Add me to a configured group and I'll "
        "greet new members with a personalised registration link."
    )


async def post_init(application: Application) -> None:
    """Runs after the Application is fully initialised."""
    group_config = load_group_config()
    admin_ids    = load_admin_ids()
    application.bot_data["group_config"] = group_config
    application.bot_data["admin_ids"]    = admin_ids
    logger.info(
        "Bot ready | tracked groups=%d | admins=%d", len(group_config), len(admin_ids)
    )


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

    app.add_handler(ChatMemberHandler(handle_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("start", start_command))

    logger.info("Starting bot (polling)…")
    app.run_polling(allowed_updates=["chat_member", "message"])


if __name__ == "__main__":
    main()
