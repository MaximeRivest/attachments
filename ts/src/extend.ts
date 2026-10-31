/**
 * For people who write their own processors and sources, and for tools
 * that read the option syntax. `import { … } from "attachments-dev/extend"`.
 *
 * @packageDocumentation
 */

export { type DslValue, formatDsl, parseDsl } from "./dsl.ts";
export { declaredOptions, type OptionDecl, type OptionType, type OptionValue, resolveOptions } from "./options.ts";
export { PageSelection, PageSelectionError, parsePages } from "./pages.ts";
export { imageTokens } from "./present.ts";
export { artifactFromWire, artifactToWire } from "./wire.ts";
