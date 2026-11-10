# Branding and Message Rules

- Default image: `https://i.ibb.co/PGpMYwYY/Gemini-Generated-Image-a7tjlia7tjlia7tj.png`
- All bot-authored text messages must use `send_branded(...)` in `branding.py`.
- `send_branded` sends the configured image with a caption, HTML formatting, and optional inline keyboard.
- Caption text is chunked because Telegram photo captions allow a maximum of 1024 characters after entity parsing.
- Do not send raw text replies from handlers; use the branded sender.
- Actual media delivery (documents/audio/video) is a separate Telegram media message. Telegram does not permit a separate photo to be attached to that same media message.
- The custom formatting parser supports B, I, U, S, CODE, PRE, Q, SPOILER and HTTP(S) LINK blocks.
- Small-caps conversion is applied to ordinary readable text, not URLs/attributes or code blocks.

The default URL is configured in `config/command_responses.json` and `.env.example`. A deployment-level `BRANDING_IMAGE_URL` value overrides the repository default, so update that environment variable too when an existing deployment still contains an older URL. `BRANDING_IMAGE_PATH` may be set to an intentional local image when local-file branding is preferred.
