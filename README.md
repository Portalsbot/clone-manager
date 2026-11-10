# Private Clone Manager

Private Telegram control bot for provisioning and managing the separate File Sharing Bot and Link Sharing Bot projects.

## Access rules
- `/start` is available to all users.
- Owner and IDs listed in `ADMIN_IDS` can use management commands.
- Non-admin users receive a private-bot warning when they run other commands.
- Maintenance mode suppresses all non-owner command responses.
- The manager records users who start it and supports user block/unblock controls.

## Registered command list
| Command | Purpose |
|---|---|
| `/start` | Welcome menu |
| `/clone` | Choose File Sharing Bot or Link Sharing Bot; asks only for BotFather token |
| `/about` | Bot information |
| `/help` | Help menu |
| `/commands` | Owner/Admin command list |
| `/settings` | Settings dashboard |
| `/broadcast` | Immediate and scheduled text/media broadcast, queue and report |
| `/users` | User lookup, info, block/unblock, activity |
| `/stats` | User, clone, period and system-health statistics |
| `/logs` | User, clone, broadcast, error and admin activity logs |
| `/ping` | Measured response latency |
| `/diagnostics` | Check Telegram, PostgreSQL, Docker daemon, product images and secret-path permissions |
| `/restart` | Restart and role-aware stop controls |
| `/maintenance` | Enable, disable and inspect maintenance mode |
| `/setmaintenance` | Maintenance notice |
| `/setstart` | Edit the welcome message |
| `/setabout` | Edit the About message |
| `/sethelp` | Edit the Help message |
| `/setimage` | Change the global message image URL |
| `/setbuttons` | Edit the Start/Help inline-button layout using JSON |
| `/setfooter` | Edit the linked footer |
| `/setquote` | Enable/disable Quote start/Quote end conversion |
| `/setname` | Change the Telegram bot display name |
| `/clones` | Clone dashboard with live Docker status |
| `/stopclone` | Select and stop a clone |
| `/restartclone` | Select and restart a clone |
| `/clonedit` | Edit clone name, token, repository/image, Docker hosting settings, encrypted environment and messages; redeploy changes |
| `/cloneinfo` | View clone details |
| `/texts` | Browse editable manager and clone messages |
| `/edittext` | Edit a selected message |

## Branding
Every bot-authored response is sent with the configured image, small-capital text, optional linked footer and a locked `· ᴄʟᴏsᴇ ·` button. The dummy URL button is removed. `(Quote start)` and `(Quote end)` are converted to Telegram blockquotes when quote formatting is enabled.

Default image: `https://i.ibb.co/PGpMYwYY/Gemini-Generated-Image-a7tjlia7tjlia7tj.png`

Default footer: `(LINK url="https://t.me/just_astha")ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴄʜᴀᴛ ᴡɪᴛʜ ᴍᴇ(/LINK)`

## Required environment
- `BOT_TOKEN`
- `DATABASE_URL`
- `OWNER_ID`
- `ADMIN_IDS` (optional, comma- or space-separated numeric Telegram IDs)
- `TOKEN_ENCRYPTION_KEY`
- `FILE_SHARING_IMAGE` and `LINK_SHARING_IMAGE`
- `GHCR_USERNAME` and `GHCR_TOKEN` if the images are private in GHCR

The owner is always included in the management allow-list. Admin IDs are separate from the owner ID. Only the configured owner and `ADMIN_IDS` receive management access.

## Run locally
```bash
python -m venv .venv
pip install -e .[dev]
cp .env.example .env
python scripts/generate_fernet_key.py
python -m clone_manager.main
```

## Current implementation boundaries
- Text and media broadcasts support preview, immediate delivery, URL buttons, scheduled delivery in Asia/Kolkata time, queue inspection/cancellation and delivery reports. Scheduled payloads persist in PostgreSQL.
- `/clonedit` is the clone configuration editor. Docker is the configured deployment backend; automatic GitHub-to-Docker image building remains intentionally out of scope.
- `/diagnostics` checks Telegram API access, PostgreSQL, Docker daemon availability, product image configuration and the clone secret directory.
- The HTTP health endpoint is `/health` when a `PORT` environment variable is supplied.
- Clone provisioning requires a working Docker daemon, pre-published File/Link images and GHCR credentials when packages are private.
- The manager must run on the same host as its Docker daemon and secret-file mount path. A normal Render web service does not expose a Docker socket, so clone creation cannot work there without a separate supported Docker host and a shared host path for secret mounts.

The Docker socket is highly privileged. Keep this bot private, restrict administrators, protect the host and secret directory, and never log plaintext BotFather tokens.

## Web-service health check and Docker requirement

When the platform supplies `PORT`, the manager starts an HTTP health endpoint at `/health`. This only reports process liveness. Run `/diagnostics` in Telegram to verify PostgreSQL and Docker. The manager cannot create clones unless it can access a Docker daemon and the daemon can mount the configured `CLONE_SECRET_DIR`. Standard hosted web-service containers do not automatically provide Docker socket access.
