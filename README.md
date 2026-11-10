# Private Clone Manager

A private Telegram control bot for provisioning and managing the separate File Sharing Bot and Link Sharing Bot projects.

## Core behaviour
- `/start` is available to everyone and displays the branded welcome menu.
- All management commands are restricted to the configured owner and admins.
- `/clone` asks for only a BotFather token, validates it with Telegram, deletes the submitted token message on a best-effort basis, encrypts the token at rest, and asks the Docker provisioner to launch the configured private image.
- `/clones` lists registered clones; `/cloneinfo` shows details; `/stopclone` and `/restartclone` accept a clone ID.
- Messages use the configured image, small-capital rendering, optional footer and a locked `· ᴄʟᴏsᴇ ·` control. The old dummy URL button has been removed.
- Quote markers `(Quote start)` and `(Quote end)` render as Telegram blockquotes.

## Required environment
- `BOT_TOKEN`
- `DATABASE_URL`
- `OWNER_ID`
- `ADMIN_IDS` (optional, comma- or space-separated numeric Telegram IDs)
- `TOKEN_ENCRYPTION_KEY`
- `FILE_SHARING_IMAGE` and `LINK_SHARING_IMAGE`
- `GHCR_USERNAME` and `GHCR_TOKEN` if the images are private in GHCR

The owner is always included in the management allow-list. Admin IDs are separate from the owner ID. `ALLOWED_USER_IDS` can be used as an additional allow-list for migration compatibility.

## Run locally
```bash
python -m venv .venv
pip install -e .[dev]
cp .env.example .env
python scripts/generate_fernet_key.py
python -m clone_manager.main
```

## Operational notes
The Docker socket grants powerful host access. Keep this bot private, restrict administrators, protect the host and secret directory, and never log plaintext BotFather tokens. The current hosting and deployment controls depend on the Docker daemon and image configuration being available.
