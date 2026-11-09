# Private Clone Manager — project foundation

This repository manages two independently versioned private bot products: File Sharing Bot and Link Sharing Bot. It is **not a public cloning service**. The current scaffold includes `/clone` with two product buttons, BotFather token validation via Telegram `getMe`, best-effort deletion of the incoming token message, Fernet encryption at rest in PostgreSQL, Docker provisioning adapter, clone listing, stop/restart commands, and common message/button editing.

## Branding

All bot-authored text replies are photo-caption messages using `https://raw.githubusercontent.com/Portalsbot/image/main/photo_2026-11-01_20-42-48.jpg` (original user-supplied page: `https://github.com/Portalsbot/image/blob/main/photo_2026-11-01_20-42-48.jpg`). Verify that the raw image is publicly fetchable by Telegram. The ZIP does not contain the image binary. Long text is split into branded photo captions; Telegram media-delivery messages remain separate media messages.

## What `/clone` does

1. Displays File Sharing Bot and Link Sharing Bot buttons.
2. Asks only for the selected bot's BotFather token.
3. Validates the token using Telegram `getMe`.
4. Deletes the token message on a best-effort basis and never logs the plaintext token.
5. Encrypts the token for database storage.
6. Pulls the configured private GHCR image and starts an isolated container.
7. Reports the resulting bot username or a deployment failure.

## Private image access

Create a GitHub fine-grained credential/PAT with only the permissions required to read packages (`read:packages`) and configure `GHCR_USERNAME` / `GHCR_TOKEN`. GitHub App installation tokens can read repository contents, but GHCR private package pulls require a registry-compatible credential; do not assume repository App tokens authenticate GHCR. Use immutable image digests in production rather than `stable` tags.

## Run locally

```bash
python -m venv .venv
pip install -e .[dev]
cp .env.example .env
python scripts/generate_fernet_key.py
# Put the generated key in TOKEN_ENCRYPTION_KEY and configure all remaining variables.
python -m clone_manager.main
```

The Docker SDK needs access to a Docker daemon. `docker-compose.yml` mounts the host Docker socket; this is highly privileged (effectively host-root access). Keep the manager private, secure the host, restrict who can use `/clone`, and never expose the Docker socket publicly.

## Important security note

The provisioner writes a per-clone JSON configuration file containing plaintext runtime secrets to `CLONE_SECRET_DIR`, restricts directories to mode 0700 and files to mode 0600, then mounts the file read-only into the clone container. The host secret directory must be on encrypted, root-controlled storage with backups/access restricted. Docker administrators can still access container files and mounted secrets. For higher assurance, migrate to Docker Swarm/Kubernetes secrets or a dedicated secret manager.

## Commands

| Command | Use |
|---|---|
| `/start` | Start private manager |
| `/clone` | Choose a product and submit one BotFather token |
| `/clones` | List your registered clone instances |
| `/stopclone CLONE_ID` | Stop an owned clone |
| `/restartclone CLONE_ID` | Restart an owned clone |
| `/cloneedit CLONE_ID TEMPLATE_KEY` | Platform-owner: edit any existing clone's text |
| `/clonepreview CLONE_ID TEMPLATE_KEY` | Platform-owner: preview an existing clone's text |
| `/clonebuttonadd CLONE_ID | KEY | LABEL | URL` | Platform-owner: add a button to a clone |
| `/clonebuttonedit CLONE_ID | KEY | INDEX | LABEL | URL` | Platform-owner: edit a clone button |
| `/clonebuttondel CLONE_ID | KEY | INDEX` | Platform-owner: delete a clone button |
| `/texts`, `/edittext`, `/previewtext`, `/resettext` | Manage manager messages |
| `/buttons`, `/addbutton`, `/delbutton` | Manage manager inline buttons |

## Master application configuration contract

The current provisioner passes `CONFIG_FILE=/run/secrets/app-config.json` and expects the master bot images to read `BOT_TOKEN`, `DATABASE_URL`, `CLONE_ID`, `OWNER_ID`, `BRANDING_IMAGE_URL` and `SMALL_CAPS` from that JSON file. Each master repository must implement this contract before the images are compatible. The provisioner writes the actual requesting Telegram owner's ID into the clone config. Clone owner permissions must still be validated with live multi-clone tests.

## Production gates not yet complete

- GitHub App installation/selected-repository integration is designed but not implemented in this ZIP.
- Private GHCR image publishing workflows are not created here; each master repository must build and publish its own image.
- The two master images must implement the exact `CONFIG_FILE` contract.
- Clone owner ID must be added to provisioning config.
- Platform-owner remote text/button overrides are stored in the shared PostgreSQL template tables using `/cloneedit`, `/clonepreview` and `/clonebutton*`. All clone instances must use the same compatible database schema and `CLONE_ID` values.
- Container health checks, quotas, cleanup/retry, updates/rollback, durable job queue, per-user clone limits and clone billing are not yet implemented.
- Central file-storage relay must be validated independently; see the File Sharing Bot README.

The manager intentionally reports provisioning failures instead of claiming success when Docker, GHCR credentials or image configuration is missing.
