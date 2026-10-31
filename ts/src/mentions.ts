/**
 * `att.fromPrompt`: the files a prompt mentions (contract/reading.md,
 * "Prompt mentions"). Mentions are untrusted: they resolve only inside
 * the root folders, never to secrets, and addresses are fetched only
 * when asked.
 *
 * @internal
 */

import type { Att, FromPromptOptions } from "./att.ts";
import { Artifacts } from "./artifacts.ts";
import { parseDslWritten } from "./dsl.ts";
import { platform } from "#platform";
import { isSecret, looksLikeKey } from "./sources/ignore.ts";
import { SPACE_CLASS } from "./text.ts";

/** Python's `\w` for text: letters, digits, `_`. */
const W = "[\\p{L}\\p{N}_]";
const NOT_W = "[^\\p{L}\\p{N}_]";

const QUOTED = new RegExp(
  "`([^`\\n]+)`" + '|"([^"\\n]+)"' + "|“([^”\\n]+)”" + `|(?<!${W})'([^'\\n]+)'(?!${W})` + "|‘([^’\\n]+)’",
  "gu",
);
const URL_RE = new RegExp(`https?://(?:(?!${SPACE_CLASS})[^<>"'\`])+`, "gu");
const URL_FULL = new RegExp(`^${URL_RE.source}$`, "u");
const BARE = new RegExp(
  `(?<!(?:${W}|[@/~.-]))` +
    `((?:~|\\.{1,2})?/?(?:(?:${W}|[.-])+/)*(?:${W}|-)(?:${W}|[.-])*\\.[A-Za-z0-9]{1,10})` +
    `(?!(?:${W}|[@-]))` +
    "(\\[[^\\]\\n]*\\])?",
  "gu",
);
void NOT_W;

export interface Mention {
  text: string;
  explicit: boolean;
  url: boolean;
  start: number;
}

function stripUrl(url: string): string {
  let dsl = "";
  const m = /\[[^\]]*\]$/u.exec(url);
  if (m) {
    dsl = m[0];
    url = url.slice(0, m.index);
  }
  url = url.replace(/[.,;:!?]+$/u, "");
  const count = (c: string): number => url.split(c).length - 1;
  while (url.endsWith(")") && count(")") > count("(")) url = url.slice(0, -1).replace(/[.,;:!?]+$/u, "");
  return url + dsl;
}

function insideBrackets(prompt: string, at: number): boolean {
  const before = prompt.slice(prompt.lastIndexOf("\n", at - 1) + 1, at);
  return before.lastIndexOf("[") > before.lastIndexOf("]");
}

/** Candidate mentions, in order of appearance. */
export function findMentions(prompt: string): Mention[] {
  const found: Mention[] = [];
  const taken: [number, number][] = [];
  const free = (start: number, end: number): boolean => taken.every(([a, b]) => end <= a || start >= b);
  for (const m of prompt.matchAll(QUOTED)) {
    const text = (m.slice(1).find((g) => g !== undefined) ?? "").trim();
    if (!text || insideBrackets(prompt, m.index)) continue;
    taken.push([m.index, m.index + m[0].length]);
    found.push({ text, explicit: true, url: URL_FULL.test(text.split("[")[0]!), start: m.index });
  }
  for (const m of prompt.matchAll(URL_RE)) {
    const span: [number, number] = [m.index, m.index + m[0].length];
    if (free(...span)) {
      taken.push(span);
      found.push({ text: stripUrl(m[0]), explicit: false, url: true, start: m.index });
    }
  }
  for (const m of prompt.matchAll(BARE)) {
    const span: [number, number] = [m.index, m.index + m[0].length];
    if (free(...span)) {
      taken.push(span);
      found.push({ text: m[1]!.replace(/\.+$/u, "") + (m[2] ?? ""), explicit: false, url: false, start: m.index });
    }
  }
  return found.sort((a, b) => a.start - b.start);
}

export async function fromPrompt(att: Att, prompt: string, options: FromPromptOptions): Promise<Artifacts> {
  const { root, urls = false, ...attOptions } = options;
  const fs = platform.fs;
  const roots = fs === null ? [] : await Promise.all((root === undefined ? [fs.cwd()] : typeof root === "string" ? [root] : [...root]).map((r) => fs.realpathLoose(r)));
  const seen = new Set<string>();
  const out = Artifacts.from([]);
  for (const mention of findMentions(prompt)) {
    const [pathText, dsl] = parseDslWritten(mention.text);
    const dslKey = JSON.stringify(Object.entries(dsl).map(([k, v]) => [k, v.text]).sort());
    if (mention.url) {
      if (!urls) continue;
      const key = `${pathText}\0${dslKey}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(...(await att(mention.text, attOptions)));
      continue;
    }
    if (fs === null || pathText.startsWith("~")) continue;
    let located: string | null = null;
    for (const r of roots) {
      const real = await fs.realpathLoose(fs.isAbsolute(pathText) ? pathText : fs.join(r, pathText));
      if (fs.inside(real, r) === null) continue;
      const info = await fs.stat(real);
      if (info?.isFile || (mention.explicit && info?.isDir)) {
        located = real;
        break;
      }
    }
    if (located === null) continue;
    const relative = roots.map((r) => fs.inside(located!, r)).find((x) => x !== null) ?? fs.basename(located);
    const info = await fs.stat(located);
    if (info?.isFile && (isSecret(relative) || looksLikeKey(await fs.readHead(located, 256)))) continue;
    const key = `${located}\0${dslKey}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const artifacts = await att(located, {
      ...attOptions,
      ...Object.fromEntries(Object.entries(dsl)),
    } as never);
    for (const a of artifacts) {
      if (a.meta.source === located || a.meta.source === fs.basename(located)) a.meta.source = pathText;
    }
    out.push(...artifacts);
  }
  return out;
}
