/**
 * Warnings go where the platform puts them: `process.emitWarning` in Node,
 * Deno and Bun (typed, so `process.on("warning")` can tell them apart and
 * `--no-warnings` silences them), `console.warn` elsewhere.
 *
 * @internal
 */

/** The kinds of warning, as Python names its warning classes. */
export type WarningType = "OptionWarning" | "RequestLimitWarning" | "AttachmentsWarning";

type Emit = (message: string, type: WarningType) => void;

const defaultEmit: Emit = (message, type) => {
  const proc = (globalThis as { process?: { emitWarning?: (m: string, o: { type: string }) => void } }).process;
  if (typeof proc?.emitWarning === "function") proc.emitWarning(message, { type });
  else console.warn(`${type}: ${message}`);
};

let emit: Emit = defaultEmit;

export function warn(message: string, type: WarningType): void {
  emit(message, type);
}

/** Collect warnings instead of emitting them while `fn` runs (tests). */
export function captureWarnings<T>(fn: () => T): { value: T; warnings: { message: string; type: WarningType }[] } {
  const caught: { message: string; type: WarningType }[] = [];
  const previous = emit;
  emit = (message, type) => caught.push({ message, type });
  try {
    return { value: fn(), warnings: caught };
  } finally {
    emit = previous;
  }
}
