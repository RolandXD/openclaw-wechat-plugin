const CHANNEL_ID = "wechat";
const DEFAULT_ACCOUNT_ID = "default";
const DEFAULT_TO = "wechat-user";

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

type WechatEntryConfig = {
  adapterUrl: string;
  outboundPath: string;
  timeoutMs: number;
  backendBaseUrl?: string;
  mode?: string;
};

type WechatAccount = {
  accountId: string;
  enabled: boolean;
  configured: boolean;
  defaultTo: string;
};

function parseEntryConfig(value: unknown): WechatEntryConfig {
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
  const channelEntry = entries[CHANNEL_ID];
  if (!isRecord(channelEntry)) {
    return {};
  }
  const entryConfig = channelEntry.config;
  return isRecord(entryConfig) ? entryConfig : {};
}

function readChannelConfig(cfg: unknown): Record<string, unknown> {
  if (!isRecord(cfg)) {
    return {};
  }
  const channels = cfg.channels;
  if (!isRecord(channels)) {
    return {};
  }
  const channelCfg = channels[CHANNEL_ID];
  return isRecord(channelCfg) ? channelCfg : {};
}

function readChannelAccounts(cfg: unknown): Record<string, unknown> {
  const channelCfg = readChannelConfig(cfg);
  const accounts = channelCfg.accounts;
  return isRecord(accounts) ? accounts : {};
}

function buildOutboundUrl(cfg: WechatEntryConfig): string {
  return `${cfg.adapterUrl}${cfg.outboundPath}`;
}

function resolveOutboundTarget(explicitTo: unknown, fallbackTo: unknown): string {
  return toNonEmptyString(explicitTo) ?? toNonEmptyString(fallbackTo) ?? DEFAULT_TO;
}

function listAccountIds(cfg: unknown): string[] {
  const ids = Object.keys(readChannelAccounts(cfg));
  if (!ids.includes(DEFAULT_ACCOUNT_ID)) {
    ids.unshift(DEFAULT_ACCOUNT_ID);
  }
  return ids;
}

function resolveAccount(cfg: unknown, accountId?: unknown): WechatAccount {
  const resolvedAccountId = toNonEmptyString(accountId) ?? DEFAULT_ACCOUNT_ID;
  const accountRaw = readChannelAccounts(cfg)[resolvedAccountId];
  const account = isRecord(accountRaw) ? accountRaw : {};
  return {
    accountId: resolvedAccountId,
    enabled: account.enabled !== false,
    configured: true,
    defaultTo: toNonEmptyString(account.defaultTo) ?? DEFAULT_TO,
  };
}

function setAccountEnabled(cfg: unknown, accountId: unknown, enabled: boolean): Record<string, unknown> {
  const safeCfg = isRecord(cfg) ? cfg : {};
  const channels = isRecord(safeCfg.channels) ? safeCfg.channels : {};
  const channelCfg = isRecord(channels[CHANNEL_ID]) ? channels[CHANNEL_ID] : {};
  const accounts = isRecord(channelCfg.accounts) ? channelCfg.accounts : {};
  const key = toNonEmptyString(accountId) ?? DEFAULT_ACCOUNT_ID;
  const account = isRecord(accounts[key]) ? accounts[key] : {};

  return {
    ...safeCfg,
    channels: {
      ...channels,
      [CHANNEL_ID]: {
        ...channelCfg,
        accounts: {
          ...accounts,
          [key]: {
            ...account,
            enabled,
          },
        },
      },
    },
  };
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
  parse(value: unknown): WechatEntryConfig {
    return parseEntryConfig(value);
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

const channelConfigSchema = {
  schema: {
    type: "object",
    additionalProperties: false,
    properties: {
      accounts: {
        type: "object",
        additionalProperties: {
          type: "object",
          additionalProperties: false,
          properties: {
            enabled: { type: "boolean" },
            defaultTo: { type: "string" },
          },
        },
      },
    },
  },
  uiHints: {
    defaultTo: {
      label: "Default To",
      help: "Default recipient when no explicit target is provided.",
    },
  },
};

const wechatChannelPlugin = {
  id: CHANNEL_ID,
  meta: {
    id: CHANNEL_ID,
    label: "WeChat",
    selectionLabel: "WeChat MiniApp",
    docsPath: "/channels/wechat",
    docsLabel: "wechat",
    blurb: "Bridge channel for WeChat mini-program delivery.",
    aliases: ["wx", "weixin"],
    order: 52,
  },
  capabilities: {
    chatTypes: ["direct"],
    polls: false,
    threads: false,
    media: false,
    reactions: false,
    edit: false,
    reply: true,
    nativeCommands: false,
  },
  reload: {
    configPrefixes: ["channels.wechat", "plugins.entries.wechat.config"],
  },
  configSchema: channelConfigSchema,
  config: {
    listAccountIds: (cfg: unknown) => listAccountIds(cfg),
    resolveAccount: (cfg: unknown, accountId?: unknown) => resolveAccount(cfg, accountId),
    defaultAccountId: () => DEFAULT_ACCOUNT_ID,
    setAccountEnabled: (args: Record<string, unknown>) =>
      setAccountEnabled(args.cfg, args.accountId, Boolean(args.enabled)),
    isConfigured: (_account: WechatAccount) => true,
    describeAccount: (account: WechatAccount) => ({
      accountId: account.accountId,
      enabled: account.enabled,
      configured: account.configured,
      defaultTo: account.defaultTo,
    }),
    resolveDefaultTo: ({ cfg, accountId }: Record<string, unknown>) =>
      resolveAccount(cfg, accountId).defaultTo,
  },
  messaging: {
    targetResolver: {
      looksLikeId: (raw: unknown) => Boolean(toNonEmptyString(raw)),
      hint: "<openid>",
    },
  },
  outbound: {
    deliveryMode: "direct",
    resolveTarget: ({ cfg, to, accountId }: Record<string, unknown>) => {
      const account = resolveAccount(cfg, accountId);
      return {
        ok: true,
        to: resolveOutboundTarget(to, account.defaultTo),
      };
    },
    sendText: async ({ cfg, to, text, accountId }: Record<string, unknown>) => {
      const entryConfig = parseEntryConfig(readPluginEntryConfig(cfg));
      const account = resolveAccount(cfg, accountId);
      const target = resolveOutboundTarget(to, account.defaultTo);
      const message = typeof text === "string" ? text : String(text ?? "");
      if (!message.trim()) {
        throw new Error("[wechat] outbound text is empty");
      }

      const payload: Record<string, unknown> = {
        channel: CHANNEL_ID,
        to: target,
        text: message,
        accountId: account.accountId,
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
        channel: CHANNEL_ID,
        externalId,
        data: response,
      };
    },
  },
};

const wechatPlugin = {
  id: CHANNEL_ID,
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
