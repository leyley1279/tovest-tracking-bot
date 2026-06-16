# Tovest Tracking Bot

A Python-based Telegram bot for the Tovest community. It automatically sends a localised welcome message with a tracked registration link whenever a new member joins one of the configured groups. It also logs every welcome message to a local SQLite database and provides an admin `/stats` command to track conversions per source.

## Features

- **Multi-Group Tracking**: Maps specific Telegram groups to specific sources (e.g. `vietnam`, `indonesia`, `global`, `social`).
- **Localised Messages**: Automatically sends the welcome message in Vietnamese, Indonesian, or English depending on the group.
- **Tracked Links**: Appends the correct UTM parameters (`?m={source}&c=1600000005`) to the registration URL.
- **SQLite Logging**: Records `user_id`, `username`, `chat_id`, `source`, and timestamp for every welcome message sent.
- **Admin Commands**: `/stats` command to view total welcome messages sent, broken down by source, and the 5 most recent events.

---

## Prerequisites

- Python 3.11+ (if running bare-metal)
- Docker & Docker Compose (if running via Docker)
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- The bot **must be added as an administrator** (or at least have permission to send messages and read chat history) in your target groups.
- You must disable "Group Privacy" in BotFather (`/setprivacy` -> Disable) so the bot can see join events.

---

## Configuration

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your details:
   - `BOT_TOKEN`: Your Telegram bot token.
   - `ADMIN_IDS`: Comma-separated list of your personal Telegram User IDs (needed to use `/stats`).
   - Group IDs: You can either set `GROUP_ID_VIETNAM`, `GROUP_ID_INDONESIA`, etc. directly in the `.env` file, OR you can point `GROUP_CONFIG_FILE` to a JSON file (e.g., `groups.json`).
     > *Note: Telegram Supergroup IDs usually start with `-100`.*

---

## Deployment Option 1: Docker (Recommended)

Docker is the easiest way to run the bot as it isolates dependencies and automatically restarts on failure.

1. Build and start the container in the background:
   ```bash
   docker-compose up -d --build
   ```

2. View the logs:
   ```bash
   docker-compose logs -f
   ```

3. Stop the bot:
   ```bash
   docker-compose down
   ```

*Note: The SQLite database and logs will be persisted in the `./data` and `./logs` directories on your host machine.*

---

## Deployment Option 2: Systemd (Bare-metal Linux VPS)

If you prefer to run the bot directly on your Ubuntu/Debian server using `systemd`:

1. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Test the bot manually:
   ```bash
   python bot.py
   ```
   *(Press `Ctrl+C` to stop)*

3. Edit the provided `tovest-bot.service` file to ensure the `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` paths correctly point to where you cloned this repository.

4. Copy the service file to systemd and enable it:
   ```bash
   sudo cp tovest-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable tovest-bot
   sudo systemctl start tovest-bot
   ```

5. Check the status and logs:
   ```bash
   sudo systemctl status tovest-bot
   journalctl -u tovest-bot -f
   ```

---

## Usage

- Add the bot to your groups.
- Ensure the bot is an admin or has send permissions.
- When a new user joins, the bot will send the localised welcome message.
- Message the bot directly (in a private chat) and type `/stats` to see the tracking metrics.
