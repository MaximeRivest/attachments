/**
 * A picture's pixel size from its first bytes (contract/presenting.md,
 * "Image sizes"): PNG, JPEG, GIF, WebP, BMP. Never throws.
 *
 * @internal
 */

const JPEG_SOF = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]);

function u16be(d: Uint8Array, i: number): number {
  return (d[i]! << 8) | d[i + 1]!;
}
function u16le(d: Uint8Array, i: number): number {
  return d[i]! | (d[i + 1]! << 8);
}
function u32be(d: Uint8Array, i: number): number {
  return ((d[i]! << 24) >>> 0) + ((d[i + 1]! << 16) | (d[i + 2]! << 8) | d[i + 3]!);
}
function u32le(d: Uint8Array, i: number): number {
  return (d[i]! | (d[i + 1]! << 8) | (d[i + 2]! << 16)) + ((d[i + 3]! << 24) >>> 0);
}
function i32le(d: Uint8Array, i: number): number {
  return d[i]! | (d[i + 1]! << 8) | (d[i + 2]! << 16) | (d[i + 3]! << 24);
}
function starts(d: Uint8Array, at: number, ascii: string): boolean {
  if (d.length < at + ascii.length) return false;
  for (let i = 0; i < ascii.length; i++) if (d[at + i] !== ascii.charCodeAt(i)) return false;
  return true;
}

function png(d: Uint8Array): [number, number] | null {
  return d.length >= 24 && starts(d, 12, "IHDR") ? [u32be(d, 16), u32be(d, 20)] : null;
}

function jpeg(d: Uint8Array): [number, number] | null {
  let i = 2;
  const n = d.length;
  while (i + 4 <= n) {
    if (d[i] !== 0xff) return null;
    const marker = d[i + 1]!;
    if (marker === 0xff) {
      i += 1;
      continue;
    }
    if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
      i += 2;
      continue;
    }
    const length = u16be(d, i + 2);
    if (JPEG_SOF.has(marker)) {
      if (i + 9 > n) return null;
      return [u16be(d, i + 7), u16be(d, i + 5)];
    }
    if (marker === 0xd9 || marker === 0xda) return null;
    i += 2 + length;
  }
  return null;
}

function gif(d: Uint8Array): [number, number] | null {
  return d.length >= 10 ? [u16le(d, 6), u16le(d, 8)] : null;
}

function webp(d: Uint8Array): [number, number] | null {
  if (d.length < 30) return null;
  if (starts(d, 12, "VP8 ")) return [u16le(d, 26) & 0x3fff, u16le(d, 28) & 0x3fff];
  if (starts(d, 12, "VP8L")) {
    const [b0, b1, b2, b3] = [d[21]!, d[22]!, d[23]!, d[24]!];
    return [1 + (((b1 & 0x3f) << 8) | b0), 1 + (((b3 & 0x0f) << 10) | (b2 << 2) | ((b1 & 0xc0) >> 6))];
  }
  if (starts(d, 12, "VP8X")) {
    return [1 + (d[24]! | (d[25]! << 8) | (d[26]! << 16)), 1 + (d[27]! | (d[28]! << 8) | (d[29]! << 16))];
  }
  return null;
}

function bmp(d: Uint8Array): [number, number] | null {
  if (d.length < 26) return null;
  if (u32le(d, 14) === 12) return [u16le(d, 18), u16le(d, 20)];
  return [Math.abs(i32le(d, 18)), Math.abs(i32le(d, 22))];
}

/** `[width, height]` in pixels, or `null` when unknown. */
export function imageSize(data: Uint8Array): [number, number] | null {
  let size: [number, number] | null = null;
  if (starts(data, 0, "\x89PNG\r\n\x1a\n")) size = png(data);
  else if (data.length >= 3 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) size = jpeg(data);
  else if (starts(data, 0, "GIF87a") || starts(data, 0, "GIF89a")) size = gif(data);
  else if (starts(data, 0, "RIFF") && starts(data, 8, "WEBP")) size = webp(data);
  else if (starts(data, 0, "BM")) size = bmp(data);
  if (size === null || size[0] <= 0 || size[1] <= 0) return null;
  return size;
}
