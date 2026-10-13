# Katarina Management — AI + Web (Freelance Paused)

Central management for three independent GitHub projects, with **AI and Web active** and **Freelance paused**:

| Lane | Repository | Allowed workflow | Boundary |
| --- | --- | --- | --- |
| AI | alfaauliau-katarinaAI/Katarina-AI | katarina-orchestrated-team.yml | ACTIVE: research and QA; no live trading |
| Freelance | alfaauliau-katarinaAI/Katarina-Freelance | freelance-source-ci.yml | PAUSED: excluded from scheduler and all-lanes mode |
| Web | alfaauliau-katarinaAI/Katarina-web | cloudflare-free-audit.yml | ACTIVE: read-only audit; no deployment |

## Architecture
Planner → up to 2 parallel active project workers → independent QA receipt checks → Manager. Project failures are isolated.

Daily scheduled audit at 08:17 WIB; manual `workflow_dispatch` selects one or all lanes. Dispatching a target repository workflow requires a separate fine-grained **Actions: Write** token and manual approval; acceptance does not mean the job passed.

## Important privacy requirement
**This repository may stay PUBLIC for AI + Web.** Never commit API tokens, secrets, client/marketplace credentials, commercial proposals, private data, or private freelance repo content. GitHub Actions secrets are masked but workflow artifacts and logs must not reveal sensitive inputs.

## GitHub Actions secrets (optional)
- Freelance is currently paused; no private-repository token is required for AI + Web audits.
- `MANAGEMENT_DISPATCH_TOKEN`: fine-grained **Actions: Write** for the three allowlisted target repositories. Required only for manually selected dispatch mode.

Neither token is required to run the local 14-test suite. No arbitrary code generation, auto-commit, bids, browser login, financial transactions, VPS cleanup, trade execution, or cross-repository source modifications occur.

## Run
GitHub Actions → **Katarina Management - AI and Web** → **Run workflow** → `scope=all` (AI + Web), `mode=audit`.

Local tests: `python -m unittest discover -s tests -v`.

Read `docs/ARCHITECTURE.md` for the permission model and report lifecycle.

Sources: [GitHub job matrices](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs), [GITHUB_TOKEN](https://docs.github.com/en/actions/security-guides/automatic-token-authentication), [Actions workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).

The original Katarina-AI, Katarina-Freelance and Katarina-web sources remain in their respective repositories. This management repository contains only orchestration.
