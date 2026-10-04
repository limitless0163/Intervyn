# AGENT_INSTRUCTIONS.md

Inspect the entire repository first, then create or update:

- `AGENTS.md`
- `frontend/AGENTS.md`
- `backend/AGENTS.md`
- `CLAUDE.md`
- `frontend/CLAUDE.md`
- `backend/CLAUDE.md`

Requirements:

- `AGENTS.md` is the source of truth for coding-agent guidance.
- Root `AGENTS.md` is the repository orientation layer: project overview, service topology, repository map, root vs. module commands, setup prerequisites, testing/logging workflow, cross-cutting conventions, and links to `frontend/AGENTS.md` and `backend/AGENTS.md`.
- Module `AGENTS.md` files contain the depth for that module: stack/dependencies, commands, architecture/source layout, development workflow, tests, code style, configuration/environment, important invariants, constraints, and non-obvious implementation rules.
- Write operational guidance for coding agents, not general README-style explanations. Prefer concrete paths, commands, symbols, boundaries, and explicit rules.
- Capture important architectural decisions and pitfalls that an agent must preserve when modifying code.
- Base everything strictly on the repository. Never invent rules, architecture, commands, or conventions.
- Avoid unnecessary duplication between root and module guides; link to the more specific guide instead.
- Keep the writing concise, technical, authoritative, and easy to scan.

Each `CLAUDE.md` must remain a minimal shim and must not duplicate guidance. Use this pattern, adapted to its scope:

```md
# CLAUDE.md

The [repo/frontend/backend] agent guidance lives in [AGENTS.md](AGENTS.md) so it is shared across coding agents (Claude Code, Codex, and others). Claude Code imports it below.

@AGENTS.md
```

All future agent guidance should live in `AGENTS.md`; `CLAUDE.md` should only import it.

Before finishing, verify that all paths, commands, architecture descriptions, and development rules match the current repository.