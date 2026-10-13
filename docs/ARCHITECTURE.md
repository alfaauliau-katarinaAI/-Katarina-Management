# Katarina Management — cross-project execution architecture

Three sibling repositories are operated through bounded GitHub-hosted Actions,
not by copying their code or granting a shared agent universal credentials.

## Dependency graph

Planner (allowlisted fixed scope) → three parallel workers (AI, Freelance,
Web; max-parallel=3, fail-fast=false) → independent QA (SHA-256 receipts tied
to the exact Git commit and run ID) → manager summary.

Every lane can report HEALTH_OK, CI_FAILED, CI_NOT_COMPLETED, DISPATCH_ACCEPTED,
BLOCKED_AUTH, BLOCKED_NETWORK or BLOCKED_CONFIG. Failure of one lane does not
stop the others. A dispatch acknowledgment is **not** verified job success.
Missing or tampered receipts fail the management handoff.

## Allowed targets

- `alfaauliau-katarinaAI/Katarina-AI`, workflow `katarina-orchestrated-team.yml`
- `alfaauliau-katarinaAI/Katarina-Freelance`, private, workflow `freelance-source-ci.yml`
- `alfaauliau-katarinaAI/Katarina-web`, workflow `cloudflare-free-audit.yml`

No arbitrary repository, workflow filename, branch or URL is supported.

## Separation of permissions

The GitHub Actions job token is read-only in THIS management repository.
A fine-grained read-only token is required to inspect the private Freelance
repository. A **separate** fine-grained Actions: Write token limited to
the three target repositories is required to trigger dispatches. It is
consumed only on a manual workflow_dispatch run with mode=dispatch.

There is **no** Contents: Write token, repo mutation, web deployment, VPS
remote shell, trading execution, automatic job applications or paid contracts.
The scheduler audits daily at 08:17 WIB; it does not dispatch on a schedule.

Secrets belong in GitHub Actions settings, never in configuration or artifacts.
The repository is currently public: make it private if management internals
should not be visible publicly.

## Reliability

Each worker times out at 8 minutes. No retries; only three parallel jobs.
QA reconstructs every checksum, source repo and commit. Manager highlights
partial blockers. Artifacts expire after seven days. Each workflow trigger
operates only when GitHub Actions executes it; no persistent agent service.

## Team responsibilities

Scheduler, QA, Manager, Security, Runner Operations, Resource Observer and
Release Safety operate centrally. Idea, Quant, Logic, Builder, Debugger,
Integration and Data workers remain in their specialist source repositories.
Freelance source QA and website audit never imply autonomous market bids,
Cloudflare writes or live trading.

References: GitHub Actions matrices, token permissions and workflow dispatch
REST documentation. These are deterministic automated workers, not independent
LLM specialists.
