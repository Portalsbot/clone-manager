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
| `/diagnostics` | Check Telegram, PostgreSQL, Render API, registry credentials and both product repositories |
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
| `/clones` | Clone dashboard with live Render service status |
| `/stopclone` | Select and stop a clone |
| `/restartclone` | Select and restart a clone |
| `/clonedit` | Edit clone name, token, repository/image, Render region and worker plan settings, encrypted environment and messages; redeploy changes |
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
- `RENDER_API_KEY`, `RENDER_WORKSPACE_ID` and `RENDER_REGISTRY_CREDENTIAL_ID`
- `FILE_SHARING_REPO_URL` / `FILE_SHARING_IMAGE` and `LINK_SHARING_REPO_URL` / `LINK_SHARING_IMAGE`

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
- `/clonedit` is the clone configuration editor. Render is the configured deployment backend. Clone Manager creates image-backed Render Background Workers from the two prebuilt private GHCR packages; GitHub repositories remain separate source projects.
- `/diagnostics` checks Telegram API access, PostgreSQL, Docker daemon availability, product image configuration and the clone secret directory.
- The HTTP health endpoint is `/health` when a `PORT` environment variable is supplied.
- Clone provisioning requires a Render API key, workspace ID, a saved Render GHCR registry credential, and published File/Link images.
- The manager must run on the same host as its Docker daemon and secret-file mount path. A normal Render web service does not expose a Docker socket, so clone creation cannot work there without a separate supported Docker host and a shared host path for secret mounts.

Keep the manager private, restrict administrators, and never log plaintext BotFather tokens or Render API credentials.

## Render Web Service and worker deployment

When the platform supplies `PORT`, the manager starts an HTTP health endpoint at `/health`. This reports process liveness. Run `/diagnostics` in Telegram to verify PostgreSQL and Render API access. The Clone Manager Web Service creates one Render Background Worker for each bot token submitted through `/clone`.

For broadcast URL buttons, include one line per button in the message: `[button] LABEL | https://URL`. The preview and final delivery preserve those URL buttons.

## Force-subscription management

Use `/fsubs` as Owner/Admin to open the unified panel. **Add** asks for a numeric channel ID and checks that the bot is an administrator; **Remove** lists active FSub channels as buttons; **Edit Message** changes the text shown to users who have not joined. Back returns to settings and Close deletes only the panel message. Owner/Admin accounts bypass membership checks. Normal users are checked before bot commands and callbacks; the panel message and Join / I've Joined buttons are sent only when they are missing membership.


## Render deployment architecture

Clone Manager is deployed from this repository as a **Render Web Service**. It uses the existing HTTP health endpoint at `/health` and runs the Telegram long-polling process in the same service.

Generated bots are **not** deployed as web services. They run as separate Render Background Workers because both products use Telegram long polling. Background Worker plans are billable; creating a clone can therefore create a paid Render resource.

The product references are intentionally fixed to the two existing private repositories:

- File Sharing source: [Portalsbot/File-Share-Bot](https://github.com/Portalsbot/File-Share-Bot)
- File Sharing image: `ghcr.io/portalsbot/file-share-bot:latest`
- Link Sharing source: [Portalsbot/link-sharing-bot](https://github.com/Portalsbot/link-sharing-bot)
- Link Sharing image: `ghcr.io/portalsbot/link-sharing-bot:latest`

The Render workspace must contain a saved `ghcr.io` registry credential with permission to pull the private packages. Set its credential ID as `RENDER_REGISTRY_CREDENTIAL_ID`. The API key, workspace ID and registry credential ID are supplied through the Clone Manager service's Render environment variables; never commit secret values to GitHub.

For generated workers, the manager passes each bot's token, the shared PostgreSQL connection, owner/admin IDs, unique `CLONE_ID`, branding image and product defaults. Link Sharing workers receive a separately generated Fernet key for their shortener credential storage.

If a worker is deleted manually in Render, its saved service ID no longer resolves. Redeploying that clone recreates the worker using its saved product/image reference.
