# Developer Best Practices

Guidelines for contributing code that passes CI on the first push. These rules are
enforced by the GitHub Actions workflows in `.github/workflows/`.

## Python (Ruff Linter)

The `lint.yml` workflow runs [Ruff](https://docs.astral.sh/ruff/) on every push.

- **No unused imports.** Remove any `import` that isn't referenced in the module.
- **Sorted imports.** Ruff enforces isort-compatible ordering:
  1. `from __future__ import ...`
  2. Standard library (`json`, `re`, `typing`, ...)
  3. Third-party (`pandas`, `streamlit`, `plotly`, ...)
  4. Local / first-party (`from demo.data_loader import ...`)
  5. One blank line separating each group, no trailing blank line before code.
- **Run locally before pushing:**
  ```bash
  python3 -m ruff check .          # lint
  python3 -m ruff check . --fix    # auto-fix safe issues
  ```

## TypeScript / CDK (infra/)

The `lint.yml` and `infra-ci.yml` workflows run `npm ci` followed by `tsc` and `jest`.

- **Peer dependency constraints matter.** `ts-jest` currently requires `typescript <7`.
  Don't bump TypeScript past the range supported by `ts-jest` without also upgrading
  `ts-jest` to a version that accepts the new TypeScript.
- **Keep `package-lock.json` in sync.** After editing `package.json`, run:
  ```bash
  cd infra && npm install --package-lock-only
  ```
- **Verify locally:**
  ```bash
  cd infra && npm ci && npm run build && npm test
  ```

## Python Dependencies (Security Audit)

The `security.yml` workflow runs `pip-audit` against pinned lock files.

- **Pin to versions available on your CI Python version.** The CI uses Python 3.11.
  Some packages (e.g., `numpy >= 2.5`) require Python 3.12+. Always check
  `Requires-Python` metadata before bumping a pinned version.
- **Lock files live in each component directory:**
  - `ai-report/requirements-lock.txt`
  - `pipeline/requirements-lock.txt` (if present)
- **Regenerate with pip-compile:**
  ```bash
  pip-compile requirements.txt --output-file=requirements-lock.txt
  ```

## General Rules

| Rule | Why |
|------|-----|
| Run the full lint suite locally before pushing | Catches 90% of CI failures in seconds |
| Don't introduce unused code in PRs | Ruff will block the merge |
| Check peer dependency ranges when upgrading | npm ERESOLVE errors break two workflows |
| Pin Python deps to versions compatible with CI Python | pip-audit installs packages to audit them |
| Keep lock files committed | Reproducible builds, no surprises in CI |

## Pre-push Checklist

```bash
# Python lint
python3 -m ruff check .

# TypeScript build
cd infra && npm ci && npm run build && npm test && cd ..

# Security audit (requires pip-audit installed)
pip-audit -r ai-report/requirements-lock.txt --no-deps
```

If all three pass locally, CI will pass.
