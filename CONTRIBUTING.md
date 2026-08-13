# Contributing to VALUATOR

Thanks for helping improve VALUATOR. Bug reports, focused feature proposals,
documentation improvements, and pull requests are welcome.

## Before opening an issue

- Search existing issues first.
- Use the bug template for reproducible defects and include the ticker, route,
  timestamp, viewport/browser, and visible unavailable or warning state.
- Never include API keys, tokens, cookies, private account data, or full
  provider payloads.
- Report security problems privately as described in [SECURITY.md](SECURITY.md).

## Development rules

- Follow [AGENTS.md](AGENTS.md), including the provider-data and UI rules.
- Before changing valuation logic, read
  [docs/valuation-calculations.md](docs/valuation-calculations.md). Do not
  invent inputs, fallback values, or formulas.
- Keep pull requests small and scoped. Add or update tests for behavior changes.
- Do not commit `.env` files, credentials, generated reports, provider caches,
  screenshots containing private data, or licensed third-party datasets.

## Required checks

Run the source gates before opening a pull request:

```bash
cd Front-End
npm run lint
npm run build

cd ../Back-End
.venv/bin/python -m pytest tests
```

GitHub Actions runs the full Docker regression on pull requests. After merge,
Jenkins reruns the full regression on `main` before production deployment.

## Pull requests

- Base changes on `main` and use a descriptive branch name.
- Explain the problem, solution, data/source impact, and verification performed.
- Include before/after screenshots for visible UI changes.
- Keep provider facts, assumptions, derived values, and unavailable states
  distinguishable in both UI and API responses.
- By contributing, you agree that your contribution is licensed under the MIT
  License.
