/**
 * SVG (contract/processors.md, "SVG"): its text, read with an XML parser
 * that agrees with Python's. No renderer here: a picture asked for is
 * a missing part, which the service draws when one is configured.
 *
 * @internal
 */

import { errorArtifact, makeArtifact, missingPart } from "../artifact.ts";
import { platform } from "#platform";
import type { ProcessorFn } from "../processors.ts";
import { strip } from "../text.ts";
import { iter, itertext, parseXml, type XmlElement } from "./xml.ts";

const TEXT_TAGS = new Set(["title", "desc", "text", "tspan", "textPath"]);
const ROOT_ATTRS = ["width", "height", "viewBox"];

function extractText(root: XmlElement): string[] {
  const lines: string[] = [];
  const skip = new Set<XmlElement>();
  for (const el of iter(root)) {
    if (skip.has(el)) continue;
    if (TEXT_TAGS.has(el.local)) {
      for (const child of iter(el)) if (child !== el) skip.add(child);
      const line = [...itertext(el)]
        .map(strip)
        .filter((t) => t)
        .join(" ");
      if (line) lines.push(line);
    }
  }
  return lines;
}

export const svgProcessor: ProcessorFn = async (raw, options, { filename }) => {
  const source = filename || "image.svg";
  let data = raw;
  const compressed = (data[0] === 0x1f && data[1] === 0x8b) || source.toLowerCase().endsWith(".svgz");
  if (compressed) {
    try {
      data = await platform.gunzip(data, 512 * 1024 * 1024);
    } catch (err) {
      return errorArtifact(source, "parse-error", `Failed to decompress SVG: ${(err as Error).message}`);
    }
  }
  let root: XmlElement;
  try {
    root = parseXml(data);
  } catch (err) {
    return errorArtifact(source, "parse-error", `Failed to parse SVG: ${(err as Error).message}`);
  }
  const lines = extractText(root);
  const extra: Record<string, unknown> = {};
  for (const attr of ROOT_ATTRS) if (attr in root.attrib) extra[attr] = root.attrib[attr];
  extra["elements"] = [...iter(root)].length;
  extra["has_text"] = lines.length > 0;
  if (compressed) extra["compressed"] = true;
  const artifact = makeArtifact({ text: lines.join("\n"), meta: { kind: "vector", extra } });
  const images = options["images"];
  if (images === "auto") extra["render_skipped"] = "no SVG renderer in this implementation";
  else if (images === true || images === "always") {
    missingPart(artifact, "svg", "Picture", "the Attachments service draws it: configure({ serviceUrl }) or set an API key");
  }
  return artifact;
};
