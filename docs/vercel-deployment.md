# Vercel production deployment

Production is deployed from the GitHub repository only after Jenkins has
completed the full `main` regression. Vercel's automatic Git deployments are
disabled in both project roots, so importing the repository does not create a
second CI path.

## Projects

| Project | Repository root | Production URL |
| --- | --- | --- |
| `valuator-thanadon912` | `Front-End` | `https://valuator-thanadon912.vercel.app` |
| `valuator-api-thanadon912` | `Back-End` | `https://valuator-api-thanadon912.vercel.app` |

Both projects point to `Thanadon912/VALUATOR`. Automatic production
domain assignment is disabled. Jenkins creates staged production deployments
from the exact 40-character Git SHA, checks backend health and frontend release
metadata, and then promotes those deployments.

The Trivy configuration scan intentionally excludes `Dockerfile.e2e`: the
official Playwright image runs browser tests as root for its browser sandbox.
That image is ephemeral, receives deterministic fixtures only, and is never
deployed. Both production Dockerfiles and both runtime images remain blocking
scan targets.

## Jenkins credentials

- `vercel-api-token`: Secret Text containing a short-lived Vercel access token.
- `valuator-production-env`: Secret File containing the production runtime
  variables plus `SUPABASE_ACCESS_TOKEN`. The deployment script uses an
  explicit allow-list, so management credentials and the Vercel token are never
  copied into a Vercel project.

`scripts/jenkins/bootstrap-jobs.sh` creates or rotates both credentials from
the local `.env` file. It also refreshes `valuator-staging-env`; secrets are
stored only in Jenkins' credential store and are masked in pipeline logs.

Required entries in the production environment file are:

```dotenv
SUPABASE_URL=
SUPABASE_PROJECT_REF=
SUPABASE_SECRET_KEY=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_ACCESS_TOKEN=
EMAIL_INTERNAL_API_TOKEN=
EMAIL_PROVIDER=gmail_smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=yourproject@gmail.com
SMTP_PASSWORD=your-google-app-password
EMAIL_FROM=yourproject@gmail.com
EMAIL_FROM_NAME=VALUATOR
SMTP_TIMEOUT_SECONDS=10
```

Provider keys are optional and follow `.env.example`. Google login remains
disabled with `GOOGLE_AUTH_ENABLED=false` until the hosted provider is
configured. Gmail SMTP credentials are copied only into the backend project;
`SMTP_PASSWORD` must be a Google App Password and is stored as a Vercel secret.

## Manual bootstrap check

The same idempotent command used by Jenkins can validate the Git links, project
roots, safe domain-assignment setting, and managed environment variables:

```bash
VERCEL_TOKEN=... python3 scripts/vercel/manage.py bootstrap --env-file .env
```

Do not pass `VERCEL_TOKEN`, `SUPABASE_ACCESS_TOKEN`, or
`SUPABASE_DB_PASSWORD` as Vercel runtime environment variables.

## Rollback

Use Vercel's deployment history to promote the immediately preceding known-good
production deployment for both projects. Roll back the frontend first and the
backend second when the API remains backward compatible; otherwise roll back
the backend first. Jenkins artifacts identify the exact tested SHA for every
release.
