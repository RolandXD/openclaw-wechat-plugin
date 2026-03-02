const DEFAULT_ADAPTER_URL = "http://127.0.0.1:8101";
const DEFAULT_OUTBOUND_PATH = "/openclaw/outbound";
const DEFAULT_TIMEOUT_MS = 15000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function toNonEmptyString(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function parseTimeoutMs(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_TIMEOUT_MS;
  }
  return Math.max(1000, Math.floor(value));
}

function normalizeBaseUrl(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function normalizePath(value: string): string {
  if (!value) {
    return DEFAULT_OUTBOUND_PATH;
  }
  return value.startsWith("/") ? value : `/${value}`;
}

type WechatPluginConfig = {
  adapterUrl: string;
  outboundPath: string;
  timeoutMs: number;
  backendBaseUrl?: string;
  mode?: string;
};

function parsePluginConfig(value: unknown): WechatPluginConfig {
  const raw = isRecord(value) ? value : {};
  return {
    adapterUrl: normalizeBaseUrl(toNonEmptyString(raw.adapterUrl) ?? DEFAULT_ADAPTER_URL),
    outboundPath: normalizePath(toNonEmptyString(raw.outboundPath) ?? DEFAULT_OUTBOUND_PATH),
    timeoutMs: parseTimeoutMs(raw.timeoutMs),
    backendBaseUrl: toNonEmptyString(raw.backendBaseUrl),
    mode: toNonEmptyString(raw.mode),
  };
}

function readPluginEntryConfig(cfg: unknown): Record<string, unknown> {
  if (!isRecord(cfg)) {
    return {};
  }
  const plugins = cfg.plugins;
  if (!isRecord(plugins)) {
    return {};
  }
  const entries = plugins.entries;
  if (!isRecord(entries)) {
    return {};
  }
  const wechatEntry = entries.wechat;
  if (!isRecord(wechatEntry)) {
    return {};
  }
  const entryConfig = wechatEntry.config;
  return isRecord(entryConfig) ? entryConfig : {};
}

function buildOutboundUrl(cfg: WechatPluginConfig): string {
  return `${cfg.adapterUrl}${cfg.outboundPath}`;
}

function resolveTarget(to: unknown, accountId: unknown): string {
  return toNonEmptyString(to) ?? toNonEmptyString(accountId) ?? "unknown";
}

async function postOutbound(
  url: string,
  timeoutMs: number,
  payload: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    const bodyText = await response.text();
    let jsonBody: Record<string, unknown> = {};
    if (bodyText.trim()) {
      try {
        const parsed = JSON.parse(bodyText);
        if (isRecord(parsed)) {
          jsonBody = parsed;
        }
      } catch {
        jsonBody = { raw: bodyText };
      }
    }

    if (!response.ok) {
      const detail = toNonEmptyString(jsonBody.detail) ?? bodyText.slice(0, 300);
      throw new Error(`[wechat] adapter HTTP ${response.status}: ${detail || "request failed"}`);
    }

    return jsonBody;
  } finally {
    clearTimeout(timer);
  }
}

const pluginConfigSchema = {
  parse(value: unknown): WechatPluginConfig {
    return parsePluginConfig(value);
  },
  uiHints: {
    adapterUrl: {
      label: "Adapter URL",
      help: "Base URL of openclaw-wechat-plugin service.",
    },
    outboundPath: {
      label: "Outbound Path",
    },
    timeoutMs: {
      label: "Timeout (ms)",
    },
  },
};

const wechatChannelPlugin = {
  id: "wechat",
  meta: {
    id: "wechat",
    label: "WeChat",
    selectionLabel: "WeChat MiniApp",
    docsPath: "/channels/wechat",
    docsLabel: "wechat",
    blurb: "Bridge channel for WeChat mini-program delivery.",
    aliases: ["wx", "weixin"],
    order: 52,
  },
  outbound: {
    deliveryMode: "direct",
    sendText: async ({ cfg, to, text, accountId }: Record<string, unknown>) => {
      const entryConfig = parsePluginConfig(readPluginEntryConfig(cfg));
      const message = typeof text === "string" ? text : String(text ?? "");
      if (!message.trim()) {
        throw new Error("[wechat] outbound text is empty");
      }

      const payload: Record<string, unknown> = {
        channel: "wechat",
        to: resolveTarget(to, accountId),
        text: message,
        accountId: toNonEmptyString(accountId) ?? null,
      };

      const url = buildOutboundUrl(entryConfig);
      const response = await postOutbound(url, entryConfig.timeoutMs, payload);
      const code = typeof response.code === "number" ? response.code : 0;
      if (code !== 0) {
        const reason = toNonEmptyString(response.message) ?? "adapter returned non-zero code";
        throw new Error(`[wechat] adapter rejected outbound message: ${reason}`);
      }

      const nested = isRecord(response.data) ? response.data : {};
      const externalId =
        toNonEmptyString(nested.external_id) ??
        toNonEmptyString(nested.externalId) ??
        toNonEmptyString(response.external_id) ??
        toNonEmptyString(response.externalId);

      return {
        ok: true,
        channel: "wechat",
        externalId,
        data: response,
      };
    },
  },
};

const wechatPlugin = {
  id: "wechat",
  name: "WeChat",
  description: "WeChat bridge plugin backed by openclaw-wechat-plugin service",
  configSchema: pluginConfigSchema,
  register(api: Record<string, unknown>) {
    const registerChannel = api.registerChannel;
    if (typeof registerChannel !== "function") {
      throw new Error("[wechat] OpenClaw registerChannel API is unavailable");
    }

    registerChannel({ plugin: wechatChannelPlugin });

    const logger = isRecord(api.logger) ? api.logger : {};
    const info = logger.info;
    if (typeof info === "function") {
      info("[wechat] channel plugin loaded");
    }
  },
};

export default wechatPlugin;
