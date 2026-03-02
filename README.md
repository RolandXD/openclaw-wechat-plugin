# openclaw-wechat-plugin

Standalone WeChat bridge service + OpenClaw extension installer.

This repo is split into two parts:
- Python service (`openclaw-wechat-plugin`) for WeChat callback/message forwarding.
- Bundled OpenClaw extension (`wechat`) that must be installed into OpenClaw to avoid `plugin not found: wechat`.

## What it does

- Exposes WeChat endpoints:
  - `GET /wechat/callback`
  - `POST /wechat/callback`
  - `POST /wechat/message`
- Forwards miniapp payloads to backend middleware (`/wechat/message`).
- Exposes `POST /openclaw/outbound` as outbound adapter endpoint for OpenClaw channel delivery.
- Can write `plugins.entries.wechat` via OpenClaw gateway API (`/openclaw/register`).
- Provides CLI command to install bundled OpenClaw extension into any OpenClaw host.
- Provides an outbound cloud connector (`openclaw-wechat-plugin connector`) so edge OpenClaw
  hosts can actively connect to a public server without inbound NAT exposure.

## Repo layout

```text
openclaw-wechat-plugin/
  openclaw_wechat_plugin/
    app.py
    cli.py
    config.py
    routes.py
    openclaw_gateway.py
    openclaw_installer.py
    openclaw_extension/
      package.json
      openclaw.plugin.json
      index.ts
  .env.example
  pyproject.toml
  main.py
```

## Installation

### 1) Install Python package

```bash
pip install "git+https://github.com/RolandXD/openclaw-wechat-plugin.git"
```

### 2) Install bundled OpenClaw extension on OpenClaw host

```bash
openclaw-wechat-plugin install-openclaw
```

Useful options:
- `--dry-run`: print commands only.
- `--openclaw-bin <path>`: specify OpenClaw executable.
- `--link`: install with `openclaw plugins install --link`.
- `--no-enable`: skip `openclaw plugins enable wechat`.

### 3) Start service

```bash
openclaw-wechat-plugin
```

### 4) Start outbound connector (recommended for private LAN/WSL hosts)

```bash
openclaw-wechat-plugin connector
```

## Configuration

Copy `.env.example` to `.env`, then configure at least:
- `WECHAT_TOKEN`
- `BACKEND_BASE_URL` (e.g. `http://127.0.0.1:8001`)
- `OPENCLAW_GATEWAY_WS_URL` (e.g. `ws://127.0.0.1:18789`)
- `OPENCLAW_TOKEN`
- `CLOUD_TUNNEL_WS_URL` (e.g. `wss://your-public-server/ws/node`)
- `CONNECTOR_NODE_ID`
- `CONNECTOR_NODE_TOKEN`

`plugins.entries.wechat.config` suggested fields:
- `adapterUrl`: plugin service base URL, e.g. `http://127.0.0.1:8101`
- `outboundPath`: default `/openclaw/outbound`
- `timeoutMs`: request timeout in ms

## APIs

- `GET /health`
- `POST /wechat/message`
- `POST /openclaw/outbound`
- `POST /openclaw/register`
- `POST /plugin/register`
- `POST /plugin/heartbeat`

## Typical flow

```text
Miniapp -> openclaw-wechat-plugin -> backend middleware -> OpenClaw/model
```

Cloud tunnel flow (single public server):

```text
Miniapp -> Public backend (HTTPS)
Edge OpenClaw host -> Public backend /ws/node (outbound WS)
Public backend -> existing WS tunnel -> edge connector -> local OpenClaw
```

## License

MIT
