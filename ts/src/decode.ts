/**
 * Decoding bytes as the text processor does (contract/reading.md, "The
 * text processor").
 *
 * @internal
 */

const utf8Strict = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });

export function latin1(data: Uint8Array): string {
  let out = "";
  for (let i = 0; i < data.length; i += 8192) out += String.fromCharCode(...data.subarray(i, i + 8192));
  return out;
}

/** UTF-8 (a byte order mark kept), else Latin-1, which decodes any bytes. */
export function guessDecode(data: Uint8Array): [encoding: "utf-8" | "latin-1", text: string] {
  try {
    return ["utf-8", utf8Strict.decode(data)];
  } catch {
    return ["latin-1", latin1(data)];
  }
}

