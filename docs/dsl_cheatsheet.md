# DSL Cheatsheet

This page provides a comprehensive list of all available DSL (Domain-Specific Language) commands in the `attachments` library. This list is generated automatically from the library's source code, so it is always up-to-date.

The cheatsheet includes:
- **Command names** and brief descriptions
- **Data types** expected for each command (string, int, boolean, etc.)
- **Default values** used when the command is not specified
- **Allowable values** for commands with restricted options
- **Context information** showing where each command is used

```{include} _generated_dsl_cheatsheet.md
```

```{note}
This cheatsheet is automatically regenerated whenever the documentation is built, both locally and in the GitHub Pages deployment. The DSL commands are discovered by analyzing the source code using AST parsing, ensuring the list is always current with the latest codebase.

**Manual regeneration:**
```bash
python scripts/generate_dsl_cheatsheet.py
```

**Automatic regeneration:**
- ✅ During local builds: `myst build`
- ✅ During GitHub Pages deployment (on push to main)