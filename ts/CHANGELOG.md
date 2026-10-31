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
- CSV and TSV, Jupyter notebooks and SVG text read here, exactly as
  Python reads them (`contract/processors.md`): CPython's newest
  `csv.Sniffer` and its `csv.reader`, a JSON parser that keeps Python's
  `NaN` and number spelling, and an XML parser that agrees with expat
  2.9 (the standard's XML declaration), checked against Python on random
  files (15,600 after the last change).
- `attachments-dev/extend`: `processor()` and `source()` of your own,
  the artifact helpers.
- Passes all 1,473 contract cases (except the two declared gaps), and
  gives exactly Python's reading of every sample file through Python's
  server.
