/**
 * Settings (contract/reading.md, "Settings"): the call's, then the
 * environment's (`ATTACHMENTS_*`), then `configure()`'s, then defaults.
 */

import { platform } from "#platform";

export type Prefer = "local" | "service" | "local-only" | "service-only";

const PREFER: readonly Prefer[] = ["local", "service", "local-only", "service-only"];

/** How `att()` reaches the Attachments service. */
export interface Settings {
  /** Key for the hosted service, or your server's key. Setting it allows sending files to the service. */
  apiKey?: string | undefined;
  /** The service's address (default `https://api.attachments.dev/v1`). Setting it allows sending files to it. */
  serviceUrl?: string | undefined;
  /** Where files are read: `local` (default: here, the service for what is missing), `service`, `local-only`, `service-only`. */
  prefer?: Prefer | undefined;
  /** Seconds to wait for the service (default 130). */
  timeout?: number | undefined;
  /** Refuse web addresses (and redirects) that resolve to private networks. For servers that fetch addresses their users give. */
  blockPrivateUrls?: boolean | undefined;
}

export const DEFAULT_SERVICE_URL = "https://api.attachments.dev/v1";
const DEFAULTS = { prefer: "local" as Prefer, serviceUrl: DEFAULT_SERVICE_URL, timeout: 130, blockPrivateUrls: false };

let configured: Settings = {};

/** @internal */
export function checkSettings(settings: Settings, where: string): void {
  const known = new Set(["apiKey", "serviceUrl", "prefer", "timeout", "blockPrivateUrls"]);
  const unknown = Object.keys(settings).filter((k) => !known.has(k));
  if (unknown.length > 0) {
    throw new TypeError(`${where}: unknown setting ${unknown.map((k) => `'${k}'`).join(", ")} (settings: ${[...known].join(", ")})`);
  }
  if (settings.prefer !== undefined && !PREFER.includes(settings.prefer)) {
    throw new TypeError(`${where}: prefer must be one of ${PREFER.join(", ")}, got ${JSON.stringify(settings.prefer)}`);
  }
  if (settings.timeout !== undefined && !(typeof settings.timeout === "number" && settings.timeout > 0)) {
    throw new TypeError(`${where}: timeout must be a number of seconds > 0, got ${JSON.stringify(settings.timeout)}`);
  }
}

/**
 * Set settings for this process (merged into earlier ones), and return
 * them. `configure()` alone returns the current settings. A server
 * answering many users should prefer `att.with(...)`, whose settings
 * belong to that `att` only.
 */
export function configure(settings: Settings = {}): Settings {
  checkSettings(settings, "configure");
  configured = { ...configured, ...Object.fromEntries(Object.entries(settings).filter(([, v]) => v !== undefined)) };
  return { ...configured };
}

/** Back to the defaults (tests). @internal */
export function resetConfig(): void {
  configured = {};
}

function fromEnv(): Settings & { error?: string } {
  const out: Settings & { error?: string } = {};
  const key = platform.env("ATTACHMENTS_API_KEY");
  if (key) out.apiKey = key;
  const url = platform.env("ATTACHMENTS_SERVICE_URL");
  if (url) out.serviceUrl = url;
  const prefer = platform.env("ATTACHMENTS_PREFER");
  if (prefer !== undefined) {
    if (!PREFER.includes(prefer as Prefer)) throw new TypeError(`Invalid ATTACHMENTS_PREFER value '${prefer}'. Valid: ${PREFER.join(", ")}`);
    out.prefer = prefer as Prefer;
  }
  const timeout = platform.env("ATTACHMENTS_TIMEOUT");
  if (timeout !== undefined) {
    const n = Number(timeout);
    if (!(timeout.trim() !== "" && Number.isFinite(n))) throw new TypeError(`Invalid ATTACHMENTS_TIMEOUT value '${timeout}': expected seconds as a number`);
    out.timeout = n;
  }
  const block = platform.env("ATT_BLOCK_PRIVATE_URLS");
  if (block !== undefined) out.blockPrivateUrls = ["1", "true", "yes", "on"].includes(block.trim().toLowerCase());
  return out;
}

/** The settings in force, and whether the service may be used. @internal */
export interface Effective {
  apiKey: string | null;
  serviceUrl: string;
  prefer: Prefer;
  timeout: number;
  blockPrivateUrls: boolean;
  /** A key or an address was set somewhere: files may be sent. */
  serviceConfigured: boolean;
}

/** @internal */
export function effective(call: Settings = {}): Effective {
  checkSettings(call, "att.with");
  const env = fromEnv();
  const pick = <K extends keyof Settings>(k: K): Settings[K] => call[k] ?? env[k] ?? configured[k];
  const apiKey = pick("apiKey") ?? null;
  const serviceUrl = pick("serviceUrl");
  return {
    apiKey,
    serviceUrl: (serviceUrl ?? DEFAULTS.serviceUrl).replace(/\/+$/u, ""),
    prefer: pick("prefer") ?? DEFAULTS.prefer,
    timeout: pick("timeout") ?? DEFAULTS.timeout,
    blockPrivateUrls: pick("blockPrivateUrls") ?? DEFAULTS.blockPrivateUrls,
    serviceConfigured: Boolean(apiKey) || serviceUrl !== undefined,
  };
}
