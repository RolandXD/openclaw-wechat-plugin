# wechat-plugin

Standalone WeChat adapter plugin service for WeClaw.

It is designed like an external channel adapter (similar to `openclawwechat` style), but runs independently from OpenClaw core:

- Handles WeChat callback signature verification
- Accepts `/wechat/message` and `/wechat/callback`
- Forwards normalized JSON payloads to backend (`/wechat/message`)
- Registers itself on OpenClaw side (`plugins.entries.wechat`) via gateway API
- Optional backend plugin registry (`/plugins/register`)

## Folder layout

```text
wechat-plugin/
  main.py
  requirements.txt
  .env.example
  plugin/
    __init__.py
    config.py
    models.py
    wechat_crypto.py
    backend_client.py
    routes.py
```

## Quick start (conda `video`)

1. Install deps:

```powershell
conda run -n video pip install -r wechat-plugin/requirements.txt
```

2. Create env file:

```powershell
Copy-Item wechat-plugin/.env.example wechat-plugin/.env
```

3. Update `wechat-plugin/.env`:

- `WECHAT_TOKEN` = your token
- `BACKEND_BASE_URL` = `http://127.0.0.1:8001`
- `OPENCLAW_GATEWAY_WS_URL` = `ws://127.0.0.1:18789`
- `OPENCLAW_TOKEN` = your OpenClaw token
- `PLUGIN_REGISTRY_TOKEN` = same as backend `PLUGIN_REGISTRY_TOKEN` (if enabled)

4. Start plugin:

```powershell
conda run -n video python wechat-plugin/main.py
```

Plugin default address: `http://127.0.0.1:8101`

## OpenClaw-side registration

On startup, plugin executes:

- `connect`
- `config.get`
- `config.apply` (or `config.set`) with `plugins.entries.wechat.enabled=true`

You can trigger it manually:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8101/openclaw/register
```

## Backend requirements (optional registry)

Main backend now exposes plugin registry:

- `POST /plugins/register`
- `POST /plugins/{instance_id}/heartbeat`
- `GET /plugins`

If you enable registry auth, set in backend `.env`:

```env
PLUGIN_REGISTRY_TOKEN=your-shared-token
```

And keep same token in `wechat-plugin/.env`.

## Miniapp integration

If miniapp should go through this plugin layer, set:

```js
API_BASE_URL = 'http://localhost:8101'
```

Flow:

```text
Miniapp -> wechat-plugin:8101 -> WeClaw backend:8001 -> OpenClaw gateway:18789
```

## Manual registration/heartbeat

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8101/openclaw/register
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8101/plugin/register
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8101/plugin/heartbeat
Invoke-RestMethod -Method Get  -Uri http://127.0.0.1:8001/plugins
```
