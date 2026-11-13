## What changed and why
<!-- Short description. Link the issue if there is one. -->

## How it was verified
- [ ] `pytest -q` and `ruff check app tests` (backend)
- [ ] `npm test` and `npm run build` (frontend)
- [ ] Manually checked the affected screens / API calls

## Checklist
- [ ] Business rules stay in `backend/app/rules` (not in React or prompts)
- [ ] New agent tools are validated, documented in `docs/AI_AGENT.md` and tested
- [ ] No secrets, real data or brand assets added
