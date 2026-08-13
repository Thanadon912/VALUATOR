# Security policy

## Supported version

Security fixes are applied to the latest commit on `main`. Older commits and
forks are not maintained by this project.

## Report a vulnerability privately

Do not open a public issue for a suspected vulnerability. Use GitHub's
[private vulnerability reporting](https://github.com/Thanadon912/VALUATOR/security/advisories/new)
so the report, reproduction details, and remediation discussion remain private.

Include the affected route or component, impact, reproduction steps, and a
minimal proof of concept when safe. Do not access data that is not yours,
degrade a provider or production service, run denial-of-service tests, or
publish the issue before a fix is available.

You should receive an acknowledgement within seven days. Confirmed reports are
prioritized by impact and may be published as a GitHub Security Advisory after
the fix is released.

## Secrets and deployment

The repository intentionally contains no production credentials. Keep API
keys, SMTP credentials, Supabase secrets, Vercel tokens, Jenkins credentials,
and internal email tokens in local or deployment environment stores. Never put
backend-only secrets in `NEXT_PUBLIC_*` variables.

Pull requests run secret scanning, dependency audits, Bandit, backend tests,
frontend lint/build checks, Supabase RLS checks, and browser regression. A
merge to `main` is deployed only after Jenkins reruns the full regression and
promotes the exact tested commit.
