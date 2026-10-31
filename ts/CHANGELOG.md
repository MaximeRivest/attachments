# Changelog (TypeScript)

## 0.1.0 (unreleased)

- `Artifacts` and every method Python has after `att()`: `text`, `toText`,
  `parts`, `claude`, `openai`, `lm15`, `chunk`, `estimateTokens`, `tokens`,
  `images`, `errors`, `throwIfErrors`, `toWire`/`fromWire`, the printed
  summary. Passes all 951 contract cases.
- `attachments-dev/extend`: `parseDsl`, `formatDsl`, `parsePages`,
  `resolveOptions`, `declaredOptions`, `imageTokens`, the wire functions.
- `att()`: paths, folders (the overview, the skip rules, `.gitignore`,
  limits), wildcard patterns, zip and tar archives, web addresses, GitHub
  repositories, `File`s and `Blob`s, lists; options in the string and in
  an object; the pending result with every method; `att.with()`,
  `att.fromPrompt()`, `att.options()`, `att.help()`; `configure()`,
  `checkDeps()`. Text is read here; every other format by the
  Attachments service when one is configured.
- `attachments-dev/extend`: `processor()` and `source()` of your own,
  the artifact helpers.
- Passes all 2,040 contract cases (except the two declared gaps), and
  gives exactly Python's reading of every sample file through Python's
  server.
