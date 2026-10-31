/**
 * What this installation reads itself. Everything else is read by the
 * service when one is configured.
 */

import { PLACEHOLDERS, processors } from "./processors.ts";
import { effective } from "./config.ts";

/**
 * Formats this installation reads itself (`true`) or leaves to the
 * service (`false`), by extension, and whether a service is configured.
 */
export function checkDeps(): { formats: Record<string, boolean>; service: boolean } {
  const formats: Record<string, boolean> = {};
  for (const [key, fn] of [...processors].sort(([a], [b]) => (a < b ? -1 : 1))) {
    if (key.startsWith("__")) continue;
    formats[key] = !PLACEHOLDERS.has(fn);
  }
  return { formats, service: effective().serviceConfigured };
}
