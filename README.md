# Katarina Management — Cross-Repository Scheduler

Central management for three independent GitHub projects:

| Lane | Repository | Allowed workflow | Boundary |
| --- | --- | --- | --- |
| AI | alfaauliau-katarinaAI/Katarina-AI | katarina-orchestrated-team.yml | Research, QA; no live trading |
| Freelance | alfaauliau-katarinaAI/Katarina-Freelance | freelance-source-ci.yml | Source QA; no job applications |
| Web | alfaauliau-katarinaAI/Katarina-web | cloudflare-free-audit.yml | Read-only audit; no deployment |

## Architecture
Planner → up to 3 parallel project workers → independent QA receipt checks → Manager. Project failures are isolated.

Daily scheduled audit at 08:17 WIB; manual `workflow_dispatch` selects one or all lanes. Dispatching a target repository workflow requires a separate fine-grained **Actions: Write** token and manual approval; acceptance does not mean the job passed.

## Important privacy requirement
**This repository was created as PUBLIC by its owner.** Switch to PRIVATE under Settings → General → Danger Zone before treating management metadata as confidential. No secrets are stored here, and credentials must never be checked in.

## GitHub Actions secrets (optional)
- `MANAGEMENT_REPO_READ_TOKEN`: fine-grained **Actions: Read** for the private Freelance repository. Without it, that lane reports BLOCKED_AUTH.
- `MANAGEMENT_DISPATCH_TOKEN`: fine-grained **Actions: Write** for the three allowlisted target repositories. Required only for manually selected dispatch mode.

Neither token is required to run the local 14-test suite. No arbitrary code generation, auto-commit, bids, browser login, financial transactions, VPS cleanup, trade execution, or cross-repository source modifications occur.

## Run
GitHub Actions → **Katarina Management - Three Parallel Projects** → **Run workflow** → `scope=all`, `mode=audit`.

Local tests: `python -m unittest discover -s tests -v`.

Read `docs/ARCHITECTURE.md` for the permission model and report lifecycle.

Sources: [GitHub job matrices](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs), [GITHUB_TOKEN](https://docs.github.com/en/actions/security-guides/automatic-token-authentication), [Actions workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).

The original Katarina-AI, Katarina-Freelance and Katarina-web sources remain in their respective repositories. This management repository contains only orchestration.
