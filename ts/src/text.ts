/**
 * The contract's text and number rules (contract/README.md, "Text, numbers
 * and white space"), where JavaScript's defaults differ: lengths and
 * offsets in code points, Python's white space, rounding half to even.
 *
 * @internal
 */

/** Python's `str.isspace()` set. Not U+FEFF, which `String.prototype.trim` removes. */
const SPACE =
  "\t\n\u000b\u000c\r\u001c\u001d\u001e\u001f \u0085\u00a0\u1680" +
  "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a" +
  "\u2028\u2029\u202f\u205f\u3000";

/** The white space class for regular expressions. */
export const SPACE_CLASS = `[${Array.from(SPACE, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`).join("")}]`;

export function isSpace(ch: string): boolean {
  return ch.length === 1 && SPACE.includes(ch);
}

/** Python's `str.strip()`. */
export function strip(text: string): string {
  let start = 0;
  let end = text.length;
  while (start < end && SPACE.includes(text[start]!)) start++;
  while (end > start && SPACE.includes(text[end - 1]!)) end--;
  return start === 0 && end === text.length ? text : text.slice(start, end);
}

/** Whether every character is white space (an empty string is). */
export function isBlank(text: string): boolean {
  for (let i = 0; i < text.length; i++) if (!SPACE.includes(text[i]!)) return false;
  return true;
}

// Without the u flag: with it, a well-formed pair is one character and does not match.
const SURROGATE = /[\ud800-\udfff]/;

/** Length in code points. */
export function cpLength(text: string): number {
  if (!SURROGATE.test(text)) return text.length;
  let n = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length) {
      const d = text.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) i++;
    }
    n++;
  }
  return n;
}

/**
 * A string indexed by code points. For text without surrogates (almost
 * all text) offsets are used as they are; otherwise a table maps each
 * code point to its UTF-16 offset.
 */
export class CodePoints {
  readonly text: string;
  readonly length: number;
  readonly #units: Uint32Array | null;

  constructor(text: string) {
    this.text = text;
    if (!SURROGATE.test(text)) {
      this.#units = null;
      this.length = text.length;
      return;
    }
    const units: number[] = [];
    for (let i = 0; i < text.length; i++) {
      units.push(i);
      const c = text.charCodeAt(i);
      if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length) {
        const d = text.charCodeAt(i + 1);
        if (d >= 0xdc00 && d <= 0xdfff) i++;
      }
    }
    units.push(text.length);
    this.#units = Uint32Array.from(units);
    this.length = units.length - 1;
  }

  /** The UTF-16 offset of code point `i` (clamped to the text). */
  unit(i: number): number {
    const clamped = Math.max(0, Math.min(this.length, i));
    return this.#units === null ? clamped : this.#units[clamped]!;
  }

  /** The code point index of UTF-16 offset `u` (which must start a code point). */
  #point(u: number): number {
    if (this.#units === null) return u;
    let lo = 0;
    let hi = this.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (this.#units[mid]! < u) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  /** `text[start:end]` in code points. */
  slice(start: number, end: number): string {
    return this.text.slice(this.unit(start), this.unit(end));
  }

  /** Python's `str.rfind(sep, lo, hi)`: the last start of `sep` lying wholly in `[lo, hi)`, or -1. */
  rfind(sep: string, lo: number, hi: number): number {
    const loU = this.unit(lo);
    const hiU = this.unit(hi);
    const at = this.text.lastIndexOf(sep, hiU - sep.length);
    if (at < loU || at < 0 || at + sep.length > hiU) return -1;
    return this.#point(at);
  }
}

/** Python's `round(x)`: to the nearest integer, ties to even. */
export function roundHalfEven(x: number): number {
  const floor = Math.floor(x);
  const diff = x - floor;
  if (diff > 0.5) return floor + 1;
  if (diff < 0.5) return floor;
  return floor % 2 === 0 ? floor : floor + 1;
}

/**
 * Python's `f"{x:.1f}"` for a non-negative finite number: the binary
 * value rounded to one decimal, ties to even. `toFixed` breaks ties up;
 * a tie needs the binary value to end exactly in .x5, which for a double
 * means a multiple of 0.25 (x × 4 an integer, x × 2 not).
 */
export function fixed1(x: number): string {
  const tie = Number.isInteger(x * 4) && !Number.isInteger(x * 2);
  if (!tie) return x.toFixed(1);
  const tenths = Math.floor(x * 10); // exact: x has two binary fraction bits
  const even = tenths % 2 === 0 ? tenths : tenths + 1;
  return (even / 10).toFixed(1);
}

/** An integer with commas between thousands (Python's `f"{n:,}"`). */
export function commas(n: number): string {
  const sign = n < 0 ? "-" : "";
  const digits = String(Math.abs(Math.trunc(n)));
  return sign + digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** Length of Python's `json.dumps(text)` (ASCII-only, with its quotes). */
export function jsonSize(text: string): number {
  let n = 2;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c === 0x22 || c === 0x5c || c === 0x0a || c === 0x0d || c === 0x09 || c === 0x08 || c === 0x0c) n += 2;
    else if (c < 0x20 || c > 0x7e) n += c === 0x7f ? 1 : 6;
    else n += 1;
  }
  return n;
}

/** Python's `x.lower()` is Unicode lowercase, as `toLowerCase` without a locale. */
export function lower(text: string): string {
  return text.toLowerCase();
}
