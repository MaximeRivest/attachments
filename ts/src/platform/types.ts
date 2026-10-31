/**
 * What `att()` needs from the machine it runs on. Node (and Deno, Bun)
 * have a file system, `git` and a guarded HTTP client; a browser has
 * `fetch` only. Chosen by the package's `#platform` import.
 *
 * @internal
 */

export interface DirEntry {
  name: string;
  /** The entry itself is a symbolic link. */
  isSymlink: boolean;
  /** A folder, not following links. */
  isDir: boolean;
}

export interface Stat {
  isFile: boolean;
  isDir: boolean;
  size: number;
}

export interface FileSystem {
  cwd(): string;
  home(): string;
  /** Absolute, normalized, links not resolved. */
  absolute(path: string): string;
  /** Links resolved; throws when the path does not exist. */
  realpath(path: string): Promise<string>;
  /** Links resolved as far as they lead (a broken link resolves to where it points). */
  realpathLoose(path: string): Promise<string>;
  /** Follows links; `null` when missing or unreadable. */
  stat(path: string): Promise<Stat | null>;
  /** Sorted by nothing in particular; throws when unreadable. */
  readdir(path: string): Promise<DirEntry[]>;
  readFile(path: string): Promise<Uint8Array>;
  /** At most `max` bytes from the start. */
  readHead(path: string, max: number): Promise<Uint8Array>;
  join(...parts: string[]): string;
  dirname(path: string): string;
  basename(path: string): string;
  /** `path` relative to `from`, with `/`; `null` when not inside it. */
  inside(path: string, from: string): string | null;
  isAbsolute(path: string): boolean;
  /** `file://` URL to a path. */
  fromFileUrl(url: string): string;
  makeTempDir(prefix: string): Promise<string>;
  remove(path: string): Promise<void>;
}

export interface Download {
  /** The address after redirects. */
  url: string;
  status: number;
  /** Lowercase names. */
  headers: Record<string, string>;
  body: Uint8Array;
}

export interface DownloadOptions {
  userAgent: string;
  maxBytes: number;
  timeoutMs: number;
  /** Refuse addresses (and redirects) that resolve to non-public addresses. */
  blockPrivate: boolean;
  signal?: AbortSignal | undefined;
}

export interface Platform {
  name: "node" | "browser";
  fs: FileSystem | null;
  env(name: string): string | undefined;
  /** Throws a `RangeError` when the output would pass `maxOutput` bytes. */
  inflateRaw(data: Uint8Array, maxOutput: number): Promise<Uint8Array>;
  /** Throws a `RangeError` when the output would pass `maxOutput` bytes. */
  gunzip(data: Uint8Array, maxOutput: number): Promise<Uint8Array>;
  download(url: string, options: DownloadOptions): Promise<Download>;
  /** `git clone --depth 1 [--branch ref] url dest`; throws on failure. */
  gitClone: ((url: string, ref: string | null, dest: string) => Promise<void>) | null;
  /** Write a warning where the platform puts warnings. */
  emitWarning(message: string, type: string): void;
}

/** A download that failed (a status, a refusal, a size cap). */
export class DownloadError extends Error {
  override name = "DownloadError";
}
