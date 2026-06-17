# Tovest Tracking Bot v3

A Python-based Telegram bot for the Tovest Trading Signal community.

The bot uses Telegram's **Join Request** feature to track which invite link a new member used when joining the group. It auto-approves every request, sends the user a localised welcome DM with a tracked registration link, and logs all events locally.

## How It Works

Three pre-existing invite links (one per traffic source) are distributed across different marketing channels. When a user clicks a link and submits a join request, the bot:

1. Reads the `invite_link` field on the `ChatJoinRequest` event.
2. Matches it against the 3 known invite links to determine the source (`vietnam`, `indonesia`, or `global`).
3. Auto-approves the join request.
4. Sends the user a private welcome message in their language with a tracked registration link and a call-to-action button.
5. Logs the event (user ID, username, source, timestamp) to a local SQLite database.

If a user joins via a direct add or an unrecognised link, the bot still approves them and logs the event with source `unknown`.

---

## Invite Link → Source Mapping

| Invite Link | Source | Language |
|---|---|---|
| `https://t.me/+i9MbIxgLhsNmYWVl` | `vietnam` | Vietnamese |
| `https://t.me/+IotrDzkFJaQzMzJl` | `indonesia` | Indonesian |
| `https://t.me/+dMnCa_n7H3Q1Njll` | `global` | English |

---

## Prerequisites

- Python 3.11+ (if running bare-metal) or Docker & Docker Compose
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- **Required group settings**:
  1. The bot must be an **administrator** in the Trading Signal group with the "Invite Users" and "Approve New Members" permissions.
  2. The group must have **"Approve New Members" (Join Requests) turned ON**.

---

## Configuration

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Fill in the required values:

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `ADMIN_IDS` | Comma-separated Telegram user IDs for admin commands |
| `GROUP_CHAT_ID` | Chat ID of the Trading Signal group (e.g. `-1001234567890`) |
| `INVITE_LINK_VN` | Pre-existing invite link for the Vietnam source |
| `INVITE_LINK_INDO` | Pre-existing invite link for the Indonesia source |
| `INVITE_LINK_GLOBAL` | Pre-existing invite link for the Global source |
| `LINK_VIETNAM` | Tracked registration URL sent to Vietnam users |
| `LINK_INDONESIA` | Tracked registration URL sent to Indonesia users |
| `LINK_GLOBAL` | Tracked registration URL sent to Global users |

---

## Admin Commands

| Command | Description |
|---|---|
| `/start` | Basic bot info (works in DM) |
| `/stats` | Show total joins and breakdown per source (admin only) |

---

## Deployment Option 1: Docker (Recommended)

1. Build and start the container:
   ```bash
   docker-compose up -d --build
   ```

2. View logs:
   ```bash
   docker-compose logs -f
   ```

3. Stop the bot:
   ```bash
   docker-compose down
   ```

The SQLite database and logs are persisted in `./data` and `./logs` on the host.

---

## Deployment Option 2: Systemd (Bare-metal Linux VPS)

1. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Edit `tovest-bot.service` so the `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` paths match your server.

3. Install and enable the service:
   ```bash
   sudo cp tovest-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable tovest-bot
   sudo systemctl start tovest-bot
   ```

4. Check status and logs:
   ```bash
   sudo systemctl status tovest-bot
   journalctl -u tovest-bot -f
   ```

---

## Notes

- **Welcome DMs require the user to have started a conversation with the bot first.** If a user has never messaged the bot, Telegram will not allow the bot to initiate a DM. The join approval will still succeed; only the DM will silently fail. This is a Telegram platform limitation.
- The `invite_links.json` file from v2 is no longer used and can be deleted.
