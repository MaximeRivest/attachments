# Attachments DSL Grammar (v1)

The DSL embeds processing options in the input string:

```
source[key: value, key2: value2, ...]
```

Every implementation, in any language, must parse it byte-for-byte identically.
The shared test vectors in [dsl-test-vectors.json](dsl-test-vectors.json) are
normative: a conforming parser passes every vector.

## Grammar (EBNF)

```ebnf
input        = source , [ options-block ] ;
options-block= "[" , [ option , { "," , option } , [ "," ] ] , "]" ;
option       = key , ":" , value ;
key          = { any character except ":" "," "]" } ;   (* trimmed *)
value        = quoted-string | bare-value ;
quoted-string= '"' , { any character except '"' } , '"'
             | "'" , { any character except "'" } , "'" ;
bare-value   = { any character except "," "]" } ;       (* trimmed *)
```

## Recognition rules

1. The options block is the **final** balanced `[...]` group, and only when the
   input **ends** with `]`. Brackets elsewhere in the source are untouched
   (`https://x.com/a[1]/b` has no options block).
2. The group is an options block only if **every** comma-separated segment
   contains a `:` (outside quotes). Otherwise the whole group is part of the
   source (`weird[1].bin` parses as a bare source). Exception: an **empty**
   group `[]` is an empty options block and is stripped.
3. Key/value are split on the **first** `:` in the segment; later colons belong
   to the value (`password: a:b` → value `a:b`).
4. Commas inside quoted values do not split options.

## Normalization

- **Keys**: trimmed, lowercased, `-` and spaces collapsed to `_`
  (`Max-Rows` → `max_rows`).
- **Duplicate keys**: last occurrence wins.
- **Values**: trimmed, then typed in this order:
  1. Quoted (`"..."`/`'...'`) → string with quotes removed, no further typing.
  2. Boolean: `true`/`false`/`yes`/`no`/`on`/`off` (case-insensitive).
     **`1` and `0` are integers, not booleans.**
  3. Integer: optional leading `-`, all digits.
  4. Float: digits containing exactly one `.`.
  5. Range: `N-M` with both sides non-negative integers → integer pair
     (represented as a two-element array in the test vectors).
  6. Otherwise: string, verbatim.

## Semantics (outside the parser)

The parser performs **no alias resolution and no validation** — it returns the
source plus raw typed options. Mapping keys to processor parameters, alias
handling (`pw` → `password`), "did you mean" suggestions, and unused-option
warnings are the router's job, driven by each processor's declared option
schema. This keeps the parser identical across languages while option
vocabularies evolve per processor.

Kwargs twin: every DSL option can be passed as a keyword argument instead
(`att("d.pdf[pages: 1-4]")` ≡ `att("d.pdf", pages="1-4")`); explicit kwargs
override DSL options on key collision.
