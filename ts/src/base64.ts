/**
 * Standard base64 (RFC 4648 §4, with padding), without Node's Buffer so
 * the same code runs in a browser.
 *
 * @internal
 */

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const VALUE = new Int16Array(128).fill(-1);
for (let i = 0; i < ALPHABET.length; i++) VALUE[ALPHABET.charCodeAt(i)] = i;

export function encode(bytes: Uint8Array): string {
  let out = "";
  const n = bytes.length;
  let i = 0;
  // Build in pieces: string concatenation of single characters is slow
  // for pictures of several megabytes.
  const pieces: string[] = [];
  for (; i + 2 < n; i += 3) {
    const v = (bytes[i]! << 16) | (bytes[i + 1]! << 8) | bytes[i + 2]!;
    out += ALPHABET[(v >> 18) & 63]! + ALPHABET[(v >> 12) & 63]! + ALPHABET[(v >> 6) & 63]! + ALPHABET[v & 63]!;
    if (out.length >= 8192) {
      pieces.push(out);
      out = "";
    }
  }
  if (i < n) {
    const v = (bytes[i]! << 16) | ((i + 1 < n ? bytes[i + 1]! : 0) << 8);
    out += ALPHABET[(v >> 18) & 63]! + ALPHABET[(v >> 12) & 63]!;
    out += i + 1 < n ? ALPHABET[(v >> 6) & 63]! + "=" : "==";
  }
  pieces.push(out);
  return pieces.join("");
}

/**
 * Decode, refusing what Python's `base64.b64decode(s, validate=True)`
 * refuses: characters outside the alphabet (white space included),
 * missing or extra padding, padding inside the data. Bits past the last
 * byte are ignored, as Python does. Returns `null` when refused.
 */
export function decodeStrict(text: string): Uint8Array | null {
  let pad = 0;
  while (pad < text.length && text.charCodeAt(text.length - 1 - pad) === 0x3d) pad++;
  const data = text.length - pad;
  if (pad > 2 || data % 4 === 1) return null;
  const want = (4 - (data % 4)) % 4;
  if (pad !== want) return null;
  const out = new Uint8Array(Math.floor((data * 3) / 4));
  let acc = 0;
  let bits = 0;
  let o = 0;
  for (let i = 0; i < data; i++) {
    const c = text.charCodeAt(i);
    const v = c < 128 ? VALUE[c]! : -1;
    if (v < 0) return null;
    acc = ((acc << 6) | v) & 0xffffff;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out[o++] = (acc >> bits) & 0xff;
    }
  }
  return out;
}

/**
 * Python's `base64.b64decode(s)` without `validate`: characters outside
 * the alphabet are dropped first. `null` when what is left is not valid.
 */
export function decodeLoose(text: string): Uint8Array | null {
  let kept = "";
  let clean = true;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c === 0x3d || (c < 128 && VALUE[c]! >= 0)) continue;
    clean = false;
    break;
  }
  if (clean) return decodeStrict(text);
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c === 0x3d || (c < 128 && VALUE[c]! >= 0)) kept += text[i];
  }
  return decodeStrict(kept);
}
