# kite-algo-minimal

Skeleton for a Zerodha Kite algo trading project (FnO + equity, paper + live).

Real content will be added later.

## Git Hooks & Documentation

Auto-generated docs ensure REST and architecture notes stay current. Before committing, enable the local hook once:

```bash
git config core.hooksPath .githooks
```

The pre-commit hook runs `python -m tools.docsync` and automatically stages `docs/` and `CHANGELOG.md` whenever they change. If the sync fails, the commit aborts so you can fix the issue first.
