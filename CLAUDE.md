# Project instructions

Server side of the IT / AI / Crypto news site: publishing API for the local pipeline (repo `agregator`), read API for
the front (`agregator-front`), admin with the review queue. Spec: `../agregator/it_ai_crypto_news_mvp.md` (§6, §7).
Stack and layout mirror `image-gallery`.

## Commit messages: Conventional Commits, always

```
<type>(<optional scope>)<optional !>: <description>
```

- Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`, `style`, `revert`.
- Scopes: `api`, `publishing`, `admin`, `publications`, `config`, `deploy`, `ci`.
- Header ≤ 150 chars, lower-case type, no trailing period.
- Breaking API/contract change: `!` after the type/scope **and** a `BREAKING CHANGE:` footer.
- No `Co-Authored-By` / "Generated with Claude" lines — the message only.

Messages drive automatic releases on `main` (python-semantic-release, `pyproject.toml`): `fix`/`perf` → patch,
`feat` → minor. Config, Docker, compose, CI or tooling changes are `build`, `ci` or `chore`, never `fix`/`feat`.
`commitlint.config.mjs` checks them.

Commit or push only when the user explicitly asks for it. The user keeps dev servers running themselves.
