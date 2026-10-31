/**
 * Page selections (contract/presenting.md, "Page selections"): `3`,
 * `2-5`, `7-`, `-1` (the last page), `-3-` (the last three), `1,3,5`.
 */

import { SPACE_CLASS, strip } from "./text.ts";

const ITEM = new RegExp(`^(-?[0-9]+)(?:${SPACE_CLASS}*-${SPACE_CLASS}*(-?[0-9]+)?)?$`, "u");

const HELP =
  'a page selection: a 1-based page (3), a range (2-5, 7-), a list written as text ("1,3,5") ' +
  "or pages counted from the end (-1 = last, -3- = last three)";

/** A value that is not a page selection. */
export class PageSelectionError extends RangeError {
  override name = "PageSelectionError";
}

/** One item: first and last page, 1-based; negative counts from the end; `null` last = to the end. */
export type PageItem = readonly [first: number, last: number | null];

export class PageSelection {
  readonly items: readonly PageItem[];

  constructor(items: readonly PageItem[]) {
    this.items = Object.freeze(items.map((i) => Object.freeze([...i]) as unknown as PageItem));
  }

  /** The 1-based pages picked from a document of `total` pages, in document order. */
  pages(total: number): number[] {
    const absolute = (n: number): number => (n > 0 ? n : total + 1 + n);
    const chosen = new Set<number>();
    for (const [first, last] of this.items) {
      const start = absolute(first);
      const end = last === null ? total : absolute(last);
      for (let p = Math.max(start, 1); p <= Math.min(end, total); p++) chosen.add(p);
    }
    return [...chosen].sort((a, b) => a - b);
  }

  /** The canonical text, e.g. `1-3,5,-1`. */
  toString(): string {
    return this.items
      .map(([first, last]) => (last === null ? `${first}-` : last === first ? `${first}` : `${first}-${last}`))
      .join(",");
  }

  toJSON(): string {
    return this.toString();
  }
}

function show(value: unknown): string {
  return typeof value === "string" ? JSON.stringify(value) : String(value);
}

/** Parse a page selection: an integer, a `[first, last]` range, or text. */
export function parsePages(value: unknown): PageSelection {
  if (value instanceof PageSelection) return value;
  let items: string[];
  if (typeof value === "number" && Number.isInteger(value)) items = [String(value)];
  else if (
    Array.isArray(value) &&
    value.length === 2 &&
    value.every((v) => typeof v === "number" && Number.isInteger(v))
  ) {
    items = [`${value[0]}-${value[1]}`];
  } else if (typeof value === "string") items = value.split(",");
  else throw new PageSelectionError(`pages must be ${HELP}, got ${show(value)}`);

  const parsed: PageItem[] = [];
  for (const raw of items) {
    const text = strip(raw);
    if (!text) continue;
    const match = ITEM.exec(text);
    if (!match) throw new PageSelectionError(`pages must be ${HELP}, got ${show(value)}`);
    const first = Number(match[1]);
    const openEnd = match[2] === undefined && text.replace(/^-+/u, "").includes("-");
    const last = openEnd ? null : Number(match[2] ?? first);
    if (first === 0 || last === 0) {
      throw new PageSelectionError(`pages must be ${HELP} (pages count from 1), got ${show(value)}`);
    }
    if (first > 0 && last !== null && last > 0 && last < first) {
      throw new PageSelectionError(`pages must be ${HELP}; ${JSON.stringify(text)} ends before it starts`);
    }
    parsed.push([first, last]);
  }
  if (parsed.length === 0) throw new PageSelectionError(`pages must be ${HELP}, got ${show(value)}`);
  return new PageSelection(parsed);
}
