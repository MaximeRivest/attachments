/**
 * "Did you mean …?": Python's `difflib.get_close_matches(word, options,
 * n=1, cutoff=0.6)`, ported so both languages suggest the same spelling
 * (contract/presenting.md, "Options"). Ratcliff/Obershelp: the ratio is
 * 2 × matched / total, matches found by CPython's `SequenceMatcher`
 * (no junk; "popular" elements of 200+ long words dropped as it does).
 *
 * @internal
 */

function matchingCount(a: string[], b: string[]): number {
  // b2j: positions of each element of b, without the popular ones.
  const b2j = new Map<string, number[]>();
  b.forEach((elt, i) => {
    const list = b2j.get(elt);
    if (list) list.push(i);
    else b2j.set(elt, [i]);
  });
  if (b.length >= 200) {
    const ntest = Math.floor(b.length / 100) + 1;
    for (const [elt, idxs] of [...b2j]) if (idxs.length > ntest) b2j.delete(elt);
  }

  const longest = (alo: number, ahi: number, blo: number, bhi: number): [number, number, number] => {
    let besti = alo;
    let bestj = blo;
    let bestsize = 0;
    let j2len = new Map<number, number>();
    for (let i = alo; i < ahi; i++) {
      const next = new Map<number, number>();
      for (const j of b2j.get(a[i]!) ?? []) {
        if (j < blo) continue;
        if (j >= bhi) break;
        const k = (j2len.get(j - 1) ?? 0) + 1;
        next.set(j, k);
        if (k > bestsize) {
          besti = i - k + 1;
          bestj = j - k + 1;
          bestsize = k;
        }
      }
      j2len = next;
    }
    // Extend over elements left out of b2j (popular ones); no junk here.
    while (besti > alo && bestj > blo && a[besti - 1] === b[bestj - 1]) {
      besti--;
      bestj--;
      bestsize++;
    }
    while (besti + bestsize < ahi && bestj + bestsize < bhi && a[besti + bestsize] === b[bestj + bestsize]) bestsize++;
    return [besti, bestj, bestsize];
  };

  let total = 0;
  const queue: [number, number, number, number][] = [[0, a.length, 0, b.length]];
  while (queue.length > 0) {
    const [alo, ahi, blo, bhi] = queue.pop()!;
    const [i, j, k] = longest(alo, ahi, blo, bhi);
    if (k > 0) {
      total += k;
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
  }
  return total;
}

/** Python's `SequenceMatcher(None, a, b).ratio()`, over code points. */
export function ratio(a: string, b: string): number {
  const ac = Array.from(a);
  const bc = Array.from(b);
  const length = ac.length + bc.length;
  return length > 0 ? (2 * matchingCount(ac, bc)) / length : 1;
}

/** The closest of `possibilities` to `word` (ratio ≥ 0.6), or `null`; ties go to the one that sorts last. */
export function closeMatch(word: string, possibilities: readonly string[], cutoff = 0.6): string | null {
  let best: [number, string] | null = null;
  for (const x of possibilities) {
    const score = ratio(x, word);
    if (score < cutoff) continue;
    if (best === null || score > best[0] || (score === best[0] && x > best[1])) best = [score, x];
  }
  return best === null ? null : best[1];
}
