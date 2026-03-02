# openclaw-wechat-plugin

Standalone WeChat adapter plugin for OpenClaw.

This service is designed to be deployed independently and registered on the OpenClaw side, similar to channel plugin onboarding.

## What it does

- Exposes WeChat endpoints:
  - `GET /wechat/callback` (signature verify)
  - `POST /wechat/callback`
  - `POST /wechat/message`
- Forwards message payloads to backend middleware (`/wechat/message`)
- Registers itself to OpenClaw gateway by writing `plugins.entries.wechat` via:
  - `connect`
  - `config.get`
  - `config.apply` or `config.set`
- Optionally registers itself to backend plugin registry (`/plugins/register`)

## Repo layout

```text
openclaw-wechat-plugin/
  openclaw_wechat_plugin/
    __init__.py
    app.py
    cli.py
    config.py
    models.py
    wechat_crypto.py
    backend_client.py
    openclaw_gateway.py
    routes.py
  .env.example
  pyproject.toml
  requirements.txt
  main.py
```

## Installation

### Option A: pip from GitHub (recommended for deployment)

```bash
pip install "git+https://github.com/RolandXD/openclaw-wechat-plugin.git"
```

Then run:

```bash
openclaw-wechat-plugin
```

### Option B: local dev

```bash
pip install -r requirements.txt
python main.py
```

## Configuration

Copy `.env.example` to `.env`, then set at least:

- `WECHAT_TOKEN`
- `BACKEND_BASE_URL` (e.g. `http://127.0.0.1:8001`)
- `OPENCLAW_GATEWAY_WS_URL` (e.g. `ws://127.0.0.1:18789`)
- `OPENCLAW_TOKEN`

### Key OpenClaw registration vars

- `OPENCLAW_AUTO_REGISTER=true`
- `OPENCLAW_APPLY_AFTER_REGISTER=true`
- `OPENCLAW_PLUGIN_ENTRY_KEY=wechat`

## APIs

- `GET /health`
- `POST /openclaw/register` (manual OpenClaw registration)
- `POST /plugin/register` (manual backend registry)
- `POST /plugin/heartbeat`

## Typical flow

```text
Miniapp -> openclaw-wechat-plugin -> backend middleware -> OpenClaw gateway/model
```

## Suggested production setup

- Keep this plugin as independent process/service.
- Register plugin into OpenClaw at startup (`OPENCLAW_AUTO_REGISTER=true`).
- Use backend registry as observability/ops metadata, not as source of truth.

## License

MIT
