/**
 * An XML 1.0 parser with namespaces that accepts and refuses what
 * Python's `ElementTree` (expat) does, and builds the same tree: elements
 * with `text` and `tail`, comments and processing instructions dropped
 * (text on both sides joined), entities from the document's own DTD
 * expanded, default attributes from its `ATTLIST`s applied.
 *
 * @internal
 */

export class XmlError extends Error {
  override name = "XmlError";
}

export interface XmlElement {
  /** `{namespace}local`, or `local` without a namespace. */
  tag: string;
  local: string;
  attrib: Record<string, string>;
  children: XmlElement[];
  text: string;
  tail: string;
}

const XML_NS = "http://www.w3.org/XML/1998/namespace";
const NAME_START = "A-Z_a-z\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD\\u{10000}-\\u{EFFFF}";
const NAME_CHAR = `${NAME_START}\\-.0-9\\u00B7\\u0300-\\u036F\\u203F-\\u2040`;
const NAME = new RegExp(`[:${NAME_START}][:${NAME_CHAR}]*`, "uy");
/** A name without a colon (namespaces in XML: NCName). */
const NCNAME = `[${NAME_START}][${NAME_CHAR}]*`;
/** `local` or `prefix:local`, as expat with namespaces requires. */
const QNAME = new RegExp(`${NCNAME}(?::${NCNAME})?(?![:${NAME_CHAR}])`, "uy");
const PI_TARGET = new RegExp(`${NCNAME}(?![:${NAME_CHAR}])`, "uy");
const INVALID_CHAR = /[^\t\n\r\u0020-\uD7FF\uE000-\uFFFD\u{10000}-\u{10FFFF}]/u;
const MAX_EXPANSION = 10_000_000;

function latin1(bytes: Uint8Array): string {
  let out = "";
  for (let i = 0; i < bytes.length; i += 8192) out += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return out;
}

/** The document as text: by its byte order mark, its declaration, or UTF-8. */
export function decodeXml(data: Uint8Array): string {
  const fatal = (label: string, bytes: Uint8Array): string => {
    try {
      return new TextDecoder(label, { fatal: true, ignoreBOM: true }).decode(bytes);
    } catch (err) {
      if (err instanceof RangeError) throw new XmlError(`unknown encoding: ${label}`);
      throw new XmlError("not well-formed (invalid token)");
    }
  };
  if (data[0] === 0xef && data[1] === 0xbb && data[2] === 0xbf) return fatal("utf-8", data.subarray(3));
  if (data[0] === 0xff && data[1] === 0xfe) return fatal("utf-16le", data.subarray(2));
  if (data[0] === 0xfe && data[1] === 0xff) return fatal("utf-16be", data.subarray(2));
  const head = latin1(data.subarray(0, 256));
  const decl = /^<\?xml[\t\n\r ][^?]*?encoding[\t\n\r ]*=[\t\n\r ]*(["'])([A-Za-z][A-Za-z0-9._-]*)\1/u.exec(head);
  if (decl) {
    const label = decl[2]!.toLowerCase();
    if (label === "iso-8859-1" || label === "latin-1" || label === "latin1" || label === "l1" || label === "iso8859-1") return latin1(data);
    if (label === "us-ascii" || label === "ascii") {
      if (data.some((b) => b > 0x7f)) throw new XmlError("not well-formed (invalid token)");
      return latin1(data);
    }
    if (label === "utf-8" || label === "utf8") return fatal("utf-8", data);
    return fatal(label, data);
  }
  return fatal("utf-8", data);
}

interface Entity {
  value: string | null; // null: external
}

interface AttDefault {
  attr: string;
  cdata: boolean;
  value: string | null;
}

/** Parse a document; throws {@link XmlError} when it is not well-formed. */
export function parseXml(data: Uint8Array): XmlElement {
  const doc = decodeXml(data).replace(/\r\n?/gu, "\n");
  const entities = new Map<string, Entity>();
  const attDefaults = new Map<string, AttDefault[]>();
  let expanded = 0;

  const fail = (message: string): never => {
    throw new XmlError(message);
  };

  // One input: the document, or an entity's replacement text.
  class Input {
    pos = 0;
    readonly text: string;
    constructor(text: string) {
      this.text = text;
    }
    get done(): boolean {
      return this.pos >= this.text.length;
    }
    starts(s: string): boolean {
      return this.text.startsWith(s, this.pos);
    }
    expect(s: string, message = "syntax error"): void {
      if (!this.starts(s)) fail(message);
      this.pos += s.length;
    }
    ws(required = false): void {
      const start = this.pos;
      while (!this.done && " \t\n\r".includes(this.text[this.pos]!)) this.pos++;
      if (required && this.pos === start) fail("syntax error");
    }
    name(pattern: RegExp = NAME, message = "not well-formed (invalid token)"): string {
      pattern.lastIndex = this.pos;
      const m = pattern.exec(this.text);
      if (!m) return fail(message);
      this.pos += m[0].length;
      return m[0];
    }
    qname(message?: string): string {
      return this.name(QNAME, message);
    }
    until(end: string, message: string): string {
      const at = this.text.indexOf(end, this.pos);
      if (at < 0) fail(message);
      const out = this.text.slice(this.pos, at);
      this.pos = at + end.length;
      return out;
    }
    quoted(): string {
      const q = this.text[this.pos];
      if (q !== '"' && q !== "'") fail("syntax error");
      this.pos++;
      return this.until(q!, "unclosed token");
    }
  }

  const charRef = (body: string): string => {
    const code = body.startsWith("#x") ? (/^#x[0-9a-fA-F]+$/u.test(body) ? parseInt(body.slice(2), 16) : NaN) : /^#[0-9]+$/u.test(body) ? parseInt(body.slice(1), 10) : NaN;
    if (!Number.isFinite(code) || code > 0x10ffff) return fail("reference to invalid character number");
    const ch = String.fromCodePoint(code);
    if (INVALID_CHAR.test(ch)) fail("reference to invalid character number");
    return ch;
  };

  const PREDEFINED: Record<string, string> = { lt: "<", gt: ">", amp: "&", apos: "'", quot: '"' };

  /** An attribute value: references expanded, white space characters as spaces. */
  const attValue = (raw: string, depth = 0): string => {
    if (raw.includes("<")) fail("not well-formed (invalid token)");
    let out = "";
    let i = 0;
    while (i < raw.length) {
      const c = raw[i]!;
      if (c === "&") {
        const end = raw.indexOf(";", i);
        if (end < 0) fail("not well-formed (invalid token)");
        const body = raw.slice(i + 1, end);
        if (body.startsWith("#")) out += charRef(body);
        else if (body in PREDEFINED) out += PREDEFINED[body];
        else {
          const e = entities.get(body);
          if (!e) fail(`undefined entity &${body};`);
          if (e!.value === null) fail("reference to external entity in attribute");
          if (depth > 40) fail("recursive entity reference");
          expanded += e!.value!.length;
          if (expanded > MAX_EXPANSION) fail("limit on input amplification factor (from DTD and entities) breached");
          out += attValue(e!.value!, depth + 1);
        }
        i = end + 1;
      } else {
        out += c === "\t" || c === "\n" || c === "\r" ? " " : c;
        i++;
      }
    }
    return out;
  };

  /** An entity's literal: character references expanded, other references kept. */
  const entityValue = (raw: string): string => {
    if (raw.includes("%")) fail("illegal parameter entity reference");
    // Every reference in the literal is complete: `&name;` or `&#…;`.
    for (const m of raw.matchAll(/&/gu)) {
      if (!new RegExp(`^&(?:#x[0-9a-fA-F]+|#[0-9]+|${NCNAME}(?::${NCNAME})?);`, "u").test(raw.slice(m.index))) {
        fail("not well-formed (invalid token)");
      }
    }
    return raw.replace(/&(#[^;]*);/gu, (_, body: string) => charRef(body));
  };

  const doctype = (input: Input): void => {
    input.expect("<!DOCTYPE");
    input.ws(true);
    input.qname("syntax error");
    input.ws();
    if (input.starts("SYSTEM")) {
      input.pos += 6;
      input.ws(true);
      input.quoted();
    } else if (input.starts("PUBLIC")) {
      input.pos += 6;
      input.ws(true);
      input.quoted();
      input.ws(true);
      input.quoted();
    }
    input.ws();
    if (input.starts("[")) {
      input.pos++;
      for (;;) {
        input.ws();
        if (input.starts("]")) {
          input.pos++;
          break;
        }
        if (input.done) fail("unclosed token");
        if (input.starts("<!--")) comment(input);
        else if (input.starts("<?")) pi(input);
        else if (input.starts("%")) {
          input.pos++;
          input.name();
          input.expect(";");
        } else if (input.starts("<!ENTITY")) {
          input.pos += 8;
          input.ws(true);
          let parameter = false;
          if (input.starts("%")) {
            parameter = true;
            input.pos++;
            input.ws(true);
          }
          const name = input.name();
          input.ws(true);
          let value: string | null;
          if (input.starts('"') || input.starts("'")) value = entityValue(input.quoted());
          else {
            if (input.starts("SYSTEM")) {
              input.pos += 6;
              input.ws(true);
              input.quoted();
            } else {
              input.expect("PUBLIC");
              input.ws(true);
              input.quoted();
              input.ws(true);
              input.quoted();
            }
            input.ws();
            if (input.starts("NDATA")) {
              input.pos += 5;
              input.ws(true);
              input.name();
            }
            value = null;
          }
          input.ws();
          input.expect(">");
          if (!parameter && !entities.has(name)) entities.set(name, { value });
        } else if (input.starts("<!ATTLIST")) {
          input.pos += 9;
          input.ws(true);
          const element = input.name();
          const list = attDefaults.get(element) ?? [];
          for (;;) {
            input.ws();
            if (input.starts(">")) {
              input.pos++;
              break;
            }
            const attr = input.name();
            input.ws(true);
            let cdata = false;
            if (input.starts("(")) input.until(")", "syntax error");
            else {
              const type = input.name();
              cdata = type === "CDATA";
              if (type === "NOTATION") {
                input.ws(true);
                input.until(")", "syntax error");
              }
            }
            input.ws(true);
            let value: string | null = null;
            if (input.starts("#REQUIRED") || input.starts("#IMPLIED")) input.pos += input.starts("#REQUIRED") ? 9 : 8;
            else {
              if (input.starts("#FIXED")) {
                input.pos += 6;
                input.ws(true);
              }
              value = attValue(input.quoted());
              if (!cdata) value = value.trim().replace(/ +/gu, " ");
            }
            if (!list.some((d) => d.attr === attr)) list.push({ attr, cdata, value });
          }
          attDefaults.set(element, list);
        } else if (input.starts("<!ELEMENT") || input.starts("<!NOTATION")) {
          // Content models and notations change nothing here: skip to the end, quotes aware.
          while (!input.done && !input.starts(">")) {
            if (input.starts('"') || input.starts("'")) input.quoted();
            else input.pos++;
          }
          input.expect(">", "unclosed token");
        } else fail("syntax error");
      }
      input.ws();
    }
    input.expect(">");
  };

  const comment = (input: Input): void => {
    input.pos += 4;
    const body = input.until("-->", "unclosed token");
    if (body.includes("--") || body.endsWith("-")) fail("not well-formed (invalid token)");
  };

  const pi = (input: Input): void => {
    input.pos += 2;
    const target = input.name(PI_TARGET);
    if (target.toLowerCase() === "xml") fail("XML or text declaration not at start of entity");
    if (!input.starts("?>")) input.ws(true); // the target, then white space or the end
    input.until("?>", "unclosed token");
  };

  // -- elements, with namespaces --------------------------------------------------------

  type Scope = Map<string, string>;
  const resolve = (qname: string, scope: Scope, isAttr: boolean): [tag: string, local: string] => {
    const colon = qname.indexOf(":");
    if (colon < 0) {
      if (isAttr) return [qname, qname];
      const uri = scope.get("");
      return [uri ? `{${uri}}${qname}` : qname, qname];
    }
    const prefix = qname.slice(0, colon);
    const local = qname.slice(colon + 1);
    if (local.includes(":") || !local) fail("not well-formed (invalid token)");
    const uri = prefix === "xml" ? XML_NS : scope.get(prefix);
    if (!uri) fail("unbound prefix");
    return [`{${uri}}${local}`, local];
  };

  let root: XmlElement | null = null;
  let sawDoctype = false;
  const stack: { el: XmlElement; qname: string; scope: Scope }[] = [];
  const addText = (s: string): void => {
    if (!s) return;
    const top = stack.at(-1);
    if (!top) {
      if (/[^ \t\n\r]/u.test(s)) fail(root ? "junk after document element" : "syntax error");
      return;
    }
    const last = top.el.children.at(-1);
    if (last) last.tail += s;
    else top.el.text += s;
  };

  const startTag = (input: Input): void => {
    input.pos++;
    const qname = input.qname();
    const raw: [string, string][] = [];
    for (;;) {
      const before = input.pos;
      input.ws();
      if (input.starts("/>") || input.starts(">")) break;
      if (input.pos === before) fail("not well-formed (invalid token)");
      const name = input.qname();
      input.ws();
      input.expect("=", "not well-formed (invalid token)");
      input.ws();
      const value = attValue(input.quoted());
      if (raw.some(([n]) => n === name)) fail("duplicate attribute");
      raw.push([name, value]);
    }
    for (const d of attDefaults.get(qname) ?? []) if (d.value !== null && !raw.some(([n]) => n === d.attr)) raw.push([d.attr, d.value]);
    const parent = stack.at(-1)?.scope ?? new Map<string, string>();
    const scope = new Map(parent);
    for (const [n, v] of raw) {
      if (n === "xmlns") scope.set("", v);
      else if (n.startsWith("xmlns:")) {
        if (!v) fail("unbound prefix");
        scope.set(n.slice(6), v);
      }
    }
    const [tag, local] = resolve(qname, scope, false);
    const attrib: Record<string, string> = {};
    for (const [n, v] of raw) {
      if (n === "xmlns" || n.startsWith("xmlns:")) continue;
      const [key] = resolve(n, scope, true);
      if (key in attrib) fail("duplicate attribute");
      attrib[key] = v;
    }
    const el: XmlElement = { tag, local, attrib, children: [], text: "", tail: "" };
    const top = stack.at(-1);
    if (top) top.el.children.push(el);
    else if (root) fail("junk after document element");
    else root = el;
    if (input.starts("/>")) input.pos += 2;
    else {
      input.pos++;
      stack.push({ el, qname, scope });
    }
  };

  const content = (input: Input, depth: number): void => {
    const baseDepth = stack.length;
    while (!input.done) {
      const lt = input.text.indexOf("<", input.pos);
      const amp = input.text.indexOf("&", input.pos);
      const next = Math.min(lt < 0 ? Infinity : lt, amp < 0 ? Infinity : amp);
      if (next > input.pos) {
        const chunk = input.text.slice(input.pos, next === Infinity ? undefined : next);
        if (chunk.includes("]]>")) fail("not well-formed (invalid token)");
        addText(chunk);
        input.pos += chunk.length;
        continue;
      }
      if (input.starts("&")) {
        if (stack.length === 0) fail(root ? "junk after document element" : "syntax error");
        const end = input.text.indexOf(";", input.pos);
        if (end < 0) fail("not well-formed (invalid token)");
        const body = input.text.slice(input.pos + 1, end);
        input.pos = end + 1;
        if (body.startsWith("#")) addText(charRef(body));
        else if (body in PREDEFINED) addText(PREDEFINED[body]!);
        else {
          if (!/^[^\s&;#]+$/u.test(body)) fail("not well-formed (invalid token)");
          const e = entities.get(body);
          if (!e || e.value === null) fail(e ? `undefined entity &${body};` : "undefined entity");
          if (depth > 40) fail("recursive entity reference");
          expanded += e!.value!.length;
          if (expanded > MAX_EXPANSION) fail("limit on input amplification factor (from DTD and entities) breached");
          const inner = new Input(e!.value!);
          content(inner, depth + 1);
        }
      } else if (input.starts("<!--")) comment(input);
      else if (input.starts("<?")) pi(input);
      else if (input.starts("<![CDATA[")) {
        if (stack.length === 0) fail("syntax error");
        input.pos += 9;
        addText(input.until("]]>", "unclosed CDATA section"));
      } else if (input.starts("<!DOCTYPE")) {
        if (root || depth > 0 || sawDoctype) fail("syntax error");
        sawDoctype = true;
        doctype(input);
      } else if (input.starts("</")) {
        input.pos += 2;
        const qname = input.qname();
        input.ws();
        input.expect(">", "not well-formed (invalid token)");
        const top = stack.pop();
        if (!top || top.qname !== qname || stack.length < baseDepth) fail("mismatched tag");
      } else if (input.starts("<")) {
        if (root && stack.length === 0) fail("junk after document element");
        startTag(input);
      }
    }
    if (depth > 0 && stack.length !== baseDepth) fail("asynchronous entity");
  };

  if (INVALID_CHAR.test(doc)) fail("not well-formed (invalid token)");
  const input = new Input(doc);
  const decl = /^<\?xml(?=[ \t\n?])/u.exec(doc);
  if (decl) {
    // version, then encoding and standalone, each optional, in that order.
    const m = /^<\?xml[ \t\n]+version[ \t\n]*=[ \t\n]*(["'])[A-Za-z0-9._-]*\1(?:[ \t\n]+encoding[ \t\n]*=[ \t\n]*(["'])[A-Za-z][A-Za-z0-9._-]*\2)?(?:[ \t\n]+standalone[ \t\n]*=[ \t\n]*(["'])(?:yes|no)\3)?[ \t\n]*\?>/u.exec(doc);
    if (!m) fail("XML declaration not well-formed");
    input.pos = m![0].length;
  }
  content(input, 0);
  if (stack.length > 0) fail("unclosed token");
  if (!root) fail("no element found");
  return root!;
}

/** Every element, the root first, in document order (`root.iter()`). */
export function* iter(el: XmlElement): Generator<XmlElement> {
  yield el;
  for (const c of el.children) yield* iter(c);
}

/** `itertext()`: an element's text, then each child's text pieces and its tail. */
export function* itertext(el: XmlElement): Generator<string> {
  if (el.text) yield el.text;
  for (const c of el.children) {
    yield* itertext(c);
    if (c.tail) yield c.tail;
  }
}
