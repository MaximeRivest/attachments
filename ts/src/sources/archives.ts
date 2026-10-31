/**
 * Zip and tar archives (contract/reading.md, "Archives"): members in the
 * archive's order, nested archives expanded, names made safe, the whole
 * expansion capped. Read the way Python's `zipfile` and `tarfile` read
 * them; no dependency.
 *
 * @internal
 */

import { READING } from "../generated/reading.ts";
import { platform } from "#platform";

const SUFFIXES: readonly string[] = READING.archive_suffixes;
const BZ2_XZ = [".tar.bz2", ".tbz2", ".tar.xz", ".txz"];

/** A member: its path inside the archive and its bytes. */
export interface Member {
  name: string;
  data: Uint8Array;
}

/** Whether a name is an archive that is expanded (not `.docx` and its kin). */
export function isArchiveName(name: string): boolean {
  const lower = name.toLowerCase();
  return SUFFIXES.some((s) => lower.endsWith(s));
}

/** `\` to `/`; empty, `.` and `..` segments and leading `/` removed. */
export function sanitizeMemberName(name: string): string {
  return name
    .replaceAll("\\", "/")
    .split("/")
    .filter((p) => p !== "" && p !== "." && p !== "..")
    .join("/");
}

const MiB = 1024 * 1024;

function limits(): { budget: number; depth: number } {
  const env = (k: string, d: number): number => {
    const v = platform.env(k);
    return v !== undefined && /^\d+$/u.test(v.trim()) ? Number(v.trim()) : d;
  };
  return { budget: env("ATT_MAX_EXPANSION_BYTES", 1024 * MiB), depth: env("ATT_MAX_ARCHIVE_DEPTH", 8) };
}

class Expansion {
  left: number;
  readonly max: number;

  constructor(left: number, max: number) {
    this.left = left;
    this.max = max;
  }

  charge(size: number, member: string): void {
    this.left -= size;
    if (this.left < 0) {
      throw new Error(
        `Archive expansion exceeds the maximum total size (${Math.floor(this.max / MiB)} MB) at member '${member}'. ` +
          "Raise ATT_MAX_EXPANSION_BYTES to override.",
      );
    }
  }
}

const isZipBytes = (d: Uint8Array): boolean => d.length >= 2 && d[0] === 0x50 && d[1] === 0x4b;
const isGzip = (d: Uint8Array): boolean => d.length >= 2 && d[0] === 0x1f && d[1] === 0x8b;
const isBz2 = (d: Uint8Array): boolean => d.length >= 3 && d[0] === 0x42 && d[1] === 0x5a && d[2] === 0x68;
const isXz = (d: Uint8Array): boolean =>
  d.length >= 6 && d[0] === 0xfd && d[1] === 0x37 && d[2] === 0x7a && d[3] === 0x58 && d[4] === 0x5a && d[5] === 0x00;

/** Thrown for `.tar.bz2` / `.tar.xz` content: the `archive/bz2-xz` extension is not here. */
export class UnsupportedArchive extends Error {
  override name = "UnsupportedArchive";
}

/**
 * Expand an archive into a flat member list. Bytes that are neither zip
 * nor tar are one member named `blob` (or the container's name).
 */
export async function explodeArchive(containerName: string, data: Uint8Array): Promise<Member[]> {
  const { budget, depth } = limits();
  return explode(containerName, data, 0, depth, new Expansion(budget, budget));
}

async function explode(containerName: string, data: Uint8Array, depth: number, maxDepth: number, expansion: Expansion): Promise<Member[]> {
  if (depth > maxDepth) {
    throw new Error(
      `Archive nesting exceeds the maximum depth (${maxDepth}) at '${containerName}'. Raise ATT_MAX_ARCHIVE_DEPTH to override.`,
    );
  }
  const name = (inner: string): string => (containerName ? `${containerName}/${inner}` : inner);
  let members: Member[] | null = null;
  if (isZipBytes(data)) members = await readZip(data, expansion, name);
  else {
    const tar = await openTar(data, expansion);
    if (tar !== null) members = readTar(tar, expansion, name);
  }
  if (members === null) return [{ name: containerName || "blob", data }];
  const out: Member[] = [];
  for (const m of members) {
    const inner = m.name.slice(containerName ? containerName.length + 1 : 0);
    if (isArchiveName(inner) && (isZipBytes(m.data) || (await openTar(m.data, expansion)) !== null)) {
      out.push(...(await explode(m.name, m.data, depth + 1, maxDepth, expansion)));
    } else out.push(m);
  }
  return out;
}

// -- zip ------------------------------------------------------------------------------

const CP437 =
  "ÇüéâäàåçêëèïîìÄÅÉæÆôöòûùÿÖÜ¢£¥₧ƒáíóúñÑªº¿⌐¬½¼¡«»░▒▓│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀αßΓπΣσµτΦΘΩδ∞φε∩≡±≥≤⌠⌡÷≈°∙·√ⁿ²■\u00a0";

function cp437(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += b < 128 ? String.fromCharCode(b) : CP437[b - 128]!;
  return s;
}

const utf8 = (bytes: Uint8Array): string => new TextDecoder("utf-8", { ignoreBOM: true }).decode(bytes);

let CRC_TABLE: Uint32Array | null = null;
function crc32(data: Uint8Array): number {
  if (CRC_TABLE === null) {
    CRC_TABLE = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      CRC_TABLE[n] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  for (const b of data) crc = CRC_TABLE[(crc ^ b) & 0xff]! ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function bad(message: string): Error {
  return new Error(message);
}

async function readZip(data: Uint8Array, expansion: Expansion, name: (inner: string) => string): Promise<Member[]> {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const u16 = (o: number): number => view.getUint16(o, true);
  const u32 = (o: number): number => view.getUint32(o, true);
  const u64 = (o: number): number => Number(view.getBigUint64(o, true));
  // End of central directory: the last 22 bytes, else searched backwards (a comment follows it).
  let eocd = -1;
  for (let i = data.length - 22; i >= Math.max(0, data.length - 22 - 65535); i--) {
    if (u32(i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw bad("File is not a zip file");
  let count = u16(eocd + 10);
  let cdSize = u32(eocd + 12);
  let cdOffset = u32(eocd + 16);
  // Zip64: a locator just before the end record.
  if (eocd >= 20 && u32(eocd - 20) === 0x07064b50) {
    const at = u64(eocd - 20 + 8);
    if (at + 56 > data.length || u32(at) !== 0x06064b50) throw bad("Corrupt zip64 end of central directory");
    count = u64(at + 32);
    cdSize = u64(at + 40);
    cdOffset = u64(at + 48);
  }
  // As Python does: the directory's position is taken from where it ends (data may be prepended).
  const concat = eocd - cdSize - cdOffset - (eocd >= 20 && u32(eocd - 20) === 0x07064b50 ? 76 : 0);
  let p = cdOffset + concat;
  const out: Member[] = [];
  for (let n = 0; n < count; n++) {
    if (p + 46 > data.length || u32(p) !== 0x02014b50) throw bad("Bad magic number for central directory");
    const flags = u16(p + 8);
    const method = u16(p + 10);
    const crc = u32(p + 16);
    let compSize = u32(p + 20);
    let size = u32(p + 24);
    const nameLen = u16(p + 28);
    const extraLen = u16(p + 30);
    const commentLen = u16(p + 32);
    let localOffset = u32(p + 42);
    const rawName = data.subarray(p + 46, p + 46 + nameLen);
    const fileName = flags & 0x800 ? utf8(rawName) : cp437(rawName);
    // Zip64 extra field: the fields that are 0xFFFFFFFF, in order.
    let e = p + 46 + nameLen;
    const extraEnd = e + extraLen;
    while (e + 4 <= extraEnd) {
      const id = u16(e);
      const len = u16(e + 2);
      if (id === 0x0001) {
        let q = e + 4;
        if (size === 0xffffffff) (size = u64(q)), (q += 8);
        if (compSize === 0xffffffff) (compSize = u64(q)), (q += 8);
        if (localOffset === 0xffffffff) localOffset = u64(q);
      }
      e += 4 + len;
    }
    p = extraEnd + commentLen;
    if (fileName.endsWith("/")) continue;
    if (flags & 0x1) throw bad(`File '${fileName}' is encrypted, password required for extraction`);
    const local = localOffset + concat;
    if (local + 30 > data.length || u32(local) !== 0x04034b50) throw bad("Bad magic number for file header");
    const localNameLen = u16(local + 26);
    const localExtraLen = u16(local + 28);
    const localName = data.subarray(local + 30, local + 30 + localNameLen);
    if (!sameBytes(localName, rawName)) throw bad(`File name in directory '${fileName}' and header differ.`);
    const start = local + 30 + localNameLen + localExtraLen;
    const raw = data.subarray(start, start + compSize);
    if (raw.length < compSize) throw bad(`File '${fileName}' is truncated`);
    const shown = name(sanitizeMemberName(fileName));
    let content: Uint8Array;
    if (method === 0) content = raw;
    else if (method === 8) {
      try {
        content = await platform.inflateRaw(raw, expansion.left + 1);
      } catch (err) {
        if (err instanceof RangeError) {
          expansion.charge(expansion.left + 1, shown);
        }
        throw bad(`Error -3 while decompressing data: ${(err as Error).message}`);
      }
    } else if (method === 12 || method === 14) {
      throw new UnsupportedArchive(`'${fileName}' is compressed with ${method === 12 ? "bzip2" : "lzma"}, which this implementation cannot read`);
    } else throw bad(`That compression method is not supported (${method})`);
    expansion.charge(content.length, shown);
    if (content.length !== size || crc32(content) !== crc) throw bad(`Bad CRC-32 for file '${fileName}'`);
    out.push({ name: shown, data: content });
  }
  return out;
}

function sameBytes(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

// -- tar ------------------------------------------------------------------------------

const BLOCK = 512;

/** The tar's bytes (decompressed), or `null` when it is not a tar. */
async function openTar(data: Uint8Array, expansion: Expansion): Promise<Uint8Array | null> {
  let tar = data;
  if (isGzip(data)) {
    try {
      tar = await platform.gunzip(data, expansion.max + 64 * MiB);
    } catch {
      return null;
    }
  } else if (isBz2(data) || isXz(data)) {
    // Only a tar inside counts; without a decoder that cannot be known here.
    throw new UnsupportedArchive("bzip2 and xz archives need the archive/bz2-xz extension, which this implementation does not have");
  }
  return firstHeader(tar) ? tar : null;
}

function octal(field: Uint8Array): number | null {
  if (field[0] === 0o200 || field[0] === 0o377) {
    let n = 0n;
    for (let i = 1; i < field.length; i++) n = (n << 8n) | BigInt(field[i]!);
    return Number(field[0] === 0o377 ? n - (1n << BigInt(8 * (field.length - 1))) : n);
  }
  const text = String.fromCharCode(...field).split("\0")[0]!.trim();
  if (text === "") return 0;
  if (!/^[0-7]+$/u.test(text)) return null;
  return parseInt(text, 8);
}

function checksumOk(header: Uint8Array): boolean {
  const stored = octal(header.subarray(148, 156));
  if (stored === null) return false;
  let unsigned = 256;
  let signed = 256;
  for (let i = 0; i < BLOCK; i++) {
    if (i >= 148 && i < 156) continue;
    unsigned += header[i]!;
    signed += header[i]! > 127 ? header[i]! - 256 : header[i]!;
  }
  return stored === unsigned || stored === signed;
}

const isZeroBlock = (h: Uint8Array): boolean => h.every((b) => b === 0);

/** Whether Python's `tarfile` opens it: an end block, or a valid first header. */
function firstHeader(tar: Uint8Array): boolean {
  if (tar.length < BLOCK) return false;
  const header = tar.subarray(0, BLOCK);
  return isZeroBlock(header) || checksumOk(header);
}

const text = (b: Uint8Array): string => utf8(b.subarray(0, b.indexOf(0) === -1 ? b.length : b.indexOf(0)));

function paxRecords(data: Uint8Array): Map<string, string> {
  const out = new Map<string, string>();
  let p = 0;
  while (p < data.length) {
    const space = data.indexOf(0x20, p);
    if (space < 0) break;
    const length = Number(String.fromCharCode(...data.subarray(p, space)));
    if (!Number.isInteger(length) || length <= 0) break;
    const record = data.subarray(space + 1, p + length - 1);
    const eq = record.indexOf(0x3d);
    if (eq > 0) out.set(utf8(record.subarray(0, eq)), utf8(record.subarray(eq + 1)));
    p += length;
  }
  return out;
}

const REGULAR = new Set(["0", "\0", "7"]);

function readTar(tar: Uint8Array, expansion: Expansion, name: (inner: string) => string): Member[] {
  const out: Member[] = [];
  let p = 0;
  let longName: string | null = null;
  let pax = new Map<string, string>();
  const global = new Map<string, string>();
  while (p + BLOCK <= tar.length) {
    const header = tar.subarray(p, p + BLOCK);
    if (isZeroBlock(header) || !checksumOk(header)) break; // the end, as tarfile reads it
    let size = octal(header.subarray(124, 136)) ?? 0;
    let type = String.fromCharCode(header[156]!);
    let memberName = text(header.subarray(0, 100));
    const prefix = text(header.subarray(345, 500));
    const dataStart = p + BLOCK;
    const next = dataStart + Math.ceil(size / BLOCK) * BLOCK;
    if (type === "L") {
      longName = text(tar.subarray(dataStart, dataStart + size));
      p = next;
      continue;
    }
    if (type === "K") {
      p = next;
      continue;
    }
    if (type === "x" || type === "g") {
      const records = paxRecords(tar.subarray(dataStart, dataStart + size));
      if (type === "g") for (const [k, v] of records) global.set(k, v);
      else pax = records;
      p = next;
      continue;
    }
    if (type === "\0" && memberName.endsWith("/")) type = "5";
    if (prefix && !["L", "K", "S"].includes(type)) memberName = `${prefix}/${memberName}`;
    if (longName !== null) memberName = longName;
    const attrs = new Map([...global, ...pax]);
    if (attrs.has("path")) memberName = attrs.get("path")!;
    if (attrs.has("size") && /^\d+$/u.test(attrs.get("size")!)) size = Number(attrs.get("size"));
    longName = null;
    pax = new Map();
    if (type === "S") throw new UnsupportedArchive(`'${memberName}' is a sparse file, which this implementation cannot read`);
    const end = dataStart + size;
    const after = dataStart + Math.ceil(size / BLOCK) * BLOCK;
    if (REGULAR.has(type)) {
      if (end > tar.length) throw new Error("unexpected end of data");
      const shown = name(sanitizeMemberName(memberName));
      expansion.charge(size, shown);
      out.push({ name: shown, data: tar.slice(dataStart, end) });
    }
    p = after;
  }
  return out;
}

export { BZ2_XZ };

/** The member names of a zip (its central directory), or `null` when it cannot be read. */
export function zipNames(data: Uint8Array): string[] | null {
  try {
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    let eocd = -1;
    for (let i = data.length - 22; i >= Math.max(0, data.length - 22 - 65535); i--) {
      if (view.getUint32(i, true) === 0x06054b50) {
        eocd = i;
        break;
      }
    }
    if (eocd < 0) return null;
    const count = view.getUint16(eocd + 10, true);
    const cdSize = view.getUint32(eocd + 12, true);
    const cdOffset = view.getUint32(eocd + 16, true);
    let p = eocd - cdSize;
    if (p < 0 || cdOffset > data.length) return null;
    const names: string[] = [];
    for (let n = 0; n < count; n++) {
      if (view.getUint32(p, true) !== 0x02014b50) return null;
      const flags = view.getUint16(p + 8, true);
      const nameLen = view.getUint16(p + 28, true);
      const raw = data.subarray(p + 46, p + 46 + nameLen);
      names.push(flags & 0x800 ? utf8(raw) : cp437(raw));
      p += 46 + nameLen + view.getUint16(p + 30, true) + view.getUint16(p + 32, true);
    }
    return names;
  } catch {
    return null;
  }
}
