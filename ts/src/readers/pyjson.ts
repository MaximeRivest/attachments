/**
 * Python's `json.loads`, and Python's `str()` of what it gives, for data
 * whose text a model will read: `NaN` and `Infinity` are accepted, and a
 * number keeps whether it was an integer (`1`) or a float (`1.0`), which
 * JavaScript's `JSON.parse` forgets.
 *
 * @internal
 */

/** A number as Python reads it. */
export class PyNumber {
  readonly float: boolean;
  /** Integers: their digits (exact at any size); floats: unused. */
  readonly digits: string;
  readonly value: number;

  constructor(float: boolean, digits: string, value: number) {
    this.float = float;
    this.digits = digits;
    this.value = value;
  }
}

export type PyJson = null | boolean | string | PyNumber | PyJson[] | { [key: string]: PyJson };

const NUMBER = /-?(?:0|[1-9]\d*)(\.\d+)?([eE][-+]?\d+)?/y;

/** Parse like Python's `json.loads`; throws `SyntaxError`. */
export function loads(text: string): PyJson {
  let i = 0;
  const ws = (): void => {
    while (i < text.length && (text[i] === " " || text[i] === "\t" || text[i] === "\n" || text[i] === "\r")) i++;
  };
  const fail = (what: string): never => {
    throw new SyntaxError(`${what} at ${i}`);
  };
  const value = (): PyJson => {
    ws();
    const c = text[i];
    if (c === "{") {
      i++;
      const out: { [key: string]: PyJson } = {};
      ws();
      if (text[i] === "}") {
        i++;
        return out;
      }
      for (;;) {
        ws();
        if (text[i] !== '"') fail("Expecting property name enclosed in double quotes");
        const key = string();
        ws();
        if (text[i] !== ":") fail("Expecting ':' delimiter");
        i++;
        out[key] = value();
        ws();
        if (text[i] === ",") {
          i++;
          continue;
        }
        if (text[i] === "}") {
          i++;
          return out;
        }
        fail("Expecting ',' delimiter");
      }
    }
    if (c === "[") {
      i++;
      const out: PyJson[] = [];
      ws();
      if (text[i] === "]") {
        i++;
        return out;
      }
      for (;;) {
        out.push(value());
        ws();
        if (text[i] === ",") {
          i++;
          continue;
        }
        if (text[i] === "]") {
          i++;
          return out;
        }
        fail("Expecting ',' delimiter");
      }
    }
    if (c === '"') return string();
    for (const [word, v] of [
      ["null", null],
      ["true", true],
      ["false", false],
      ["NaN", new PyNumber(true, "", NaN)],
      ["Infinity", new PyNumber(true, "", Infinity)],
      ["-Infinity", new PyNumber(true, "", -Infinity)],
    ] as const) {
      if (text.startsWith(word, i)) {
        i += word.length;
        return v;
      }
    }
    NUMBER.lastIndex = i;
    const m = NUMBER.exec(text);
    if (m) {
      i += m[0].length;
      if (m[1] === undefined && m[2] === undefined) {
        const digits = m[0] === "-0" ? "0" : m[0];
        return new PyNumber(false, digits, Number(digits));
      }
      return new PyNumber(true, "", Number(m[0]));
    }
    return fail("Expecting value");
  };
  const string = (): string => {
    i++;
    let out = "";
    for (;;) {
      const c = text[i];
      if (c === undefined) fail("Unterminated string");
      if (c === '"') {
        i++;
        return out;
      }
      if (c === "\\") {
        const e = text[i + 1];
        const simple: Record<string, string> = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
        if (e !== undefined && e in simple) {
          out += simple[e];
          i += 2;
        } else if (e === "u" && /^[0-9a-fA-F]{4}$/u.test(text.slice(i + 2, i + 6))) {
          out += String.fromCharCode(parseInt(text.slice(i + 2, i + 6), 16));
          i += 6;
        } else fail("Invalid \\escape");
        continue;
      }
      if (c!.charCodeAt(0) < 0x20) fail("Invalid control character");
      out += c;
      i++;
    }
  };
  const result = value();
  ws();
  if (i < text.length) fail("Extra data");
  return result;
}

/** Python's `repr(float)`. */
export function floatRepr(x: number): string {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  const sign = x < 0 ? "-" : "";
  const [mantissa, exp] = Math.abs(x).toExponential().split("e") as [string, string];
  const digits = mantissa.replace(".", "");
  const decpt = Number(exp) + 1;
  if (decpt <= -4 || decpt > 16) {
    const e = decpt - 1;
    const body = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
    return `${sign}${body}e${e < 0 ? "-" : "+"}${String(Math.abs(e)).padStart(2, "0")}`;
  }
  if (decpt <= 0) return `${sign}0.${"0".repeat(-decpt)}${digits}`;
  if (decpt >= digits.length) return `${sign}${digits}${"0".repeat(decpt - digits.length)}.0`;
  return `${sign}${digits.slice(0, decpt)}.${digits.slice(decpt)}`;
}

function strRepr(s: string): string {
  const quote = s.includes("'") && !s.includes('"') ? '"' : "'";
  let out = "";
  for (const ch of s) {
    const c = ch.codePointAt(0)!;
    if (ch === "\\") out += "\\\\";
    else if (ch === quote) out += `\\${quote}`;
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (c < 0x20 || c === 0x7f) out += `\\x${c.toString(16).padStart(2, "0")}`;
    else out += ch;
  }
  return quote + out + quote;
}

/** Python's `repr()` of a parsed value. */
export function pyRepr(v: PyJson): string {
  if (typeof v === "string") return strRepr(v);
  if (Array.isArray(v)) return `[${v.map(pyRepr).join(", ")}]`;
  if (v !== null && typeof v === "object" && !(v instanceof PyNumber)) {
    return `{${Object.entries(v)
      .map(([k, x]) => `${strRepr(k)}: ${pyRepr(x)}`)
      .join(", ")}}`;
  }
  return pyStr(v);
}

/** Python's `str()` of a parsed value. */
export function pyStr(v: PyJson): string {
  if (typeof v === "string") return v;
  if (v === null) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (v instanceof PyNumber) return v.float ? floatRepr(v.value) : v.digits;
  return pyRepr(v);
}

/** The plain JSON value (numbers as numbers), for `meta`. */
export function plain(v: PyJson): unknown {
  if (v instanceof PyNumber) return v.value;
  if (Array.isArray(v)) return v.map(plain);
  if (v !== null && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, plain(x)]));
  return v;
}

/** Python's truthiness of a parsed value. */
export function truthy(v: PyJson | undefined): boolean {
  if (v === undefined || v === null || v === false || v === "") return false;
  if (v instanceof PyNumber) return v.value !== 0;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "object") return Object.keys(v).length > 0;
  return true;
}

export const isDict = (v: PyJson | undefined): v is { [key: string]: PyJson } =>
  v !== null && v !== undefined && typeof v === "object" && !Array.isArray(v) && !(v instanceof PyNumber);
