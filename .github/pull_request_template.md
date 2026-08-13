## Problem and scope

<!-- What problem does this solve? Keep the change focused. -->

## Implementation

<!-- Summarize the solution and important trade-offs. -->

## Data and valuation impact

<!-- List affected providers, source provenance, assumptions, formulas, and unavailable states. Write “None” when not applicable. -->

## Verification

- [ ] `cd Front-End && npm run lint`
- [ ] `cd Front-End && npm run build`
- [ ] `cd Back-End && .venv/bin/python -m pytest tests`
- [ ] Relevant browser or API regression was added or run
- [ ] No credentials, environment files, private data, or provider dumps are included
- [ ] UI screenshots are attached when the visual behavior changed

## Checklist

- [ ] I followed `AGENTS.md`.
- [ ] I read `docs/valuation-calculations.md` before changing valuation logic, or this change does not touch valuation logic.
- [ ] Missing source inputs remain unavailable instead of receiving invented fallback values.
