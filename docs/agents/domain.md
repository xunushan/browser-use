# Domain Docs

## Layout

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root.

## Consumer rules

Skills that read domain docs (`/improve-codebase-architecture`, `/diagnosing-bugs`, `/tdd`) should:

1. Read `CONTEXT.md` first to learn the project's domain language
2. Read `docs/adr/` for past architectural decisions
3. Treat `CONTEXT.md` as the single source of truth for terminology

## Files

- `CONTEXT.md` — Project domain language and glossary
- `docs/adr/` — Architecture Decision Records
