"""Cross-repository research management with strict lane allowlisting."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

PROJECTS = ("ai", "freelance", "web")
SCOPES = (*PROJECTS, "all")
MODES = ("audit", "dispatch")
MANIFEST_VERSION = 1
OWNER = "alfaauliau-katarinaAI"
MAX_PARALLEL = 3
RECEIPT_VERSION = "KATARINA_MANAGEMENT_1"
REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
WORKFLOW = re.compile(r"^[A-Za-z0-9_.-]+\.ya?ml$")


def encode(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8")


def sha(payload: dict) -> str:
    return sha256(encode(payload)).hexdigest()


def signed(payload: dict) -> dict:
    data = dict(payload)
    data["receipt_sha256"] = sha(data)
    return data


def verify_receipt(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError("record_must_be_object")
    data = dict(record)
    fingerprint = data.pop("receipt_sha256", None)
    if not isinstance(fingerprint, str) or fingerprint != sha(data):
        raise ValueError("invalid_receipt_checksum")
    return data


def load_manifest(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 16000:
        raise ValueError("missing_or_oversized_manifest")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if (cfg.get("schema_version") != MANIFEST_VERSION or
            cfg.get("owner") != OWNER or
            cfg.get("max_parallel") != MAX_PARALLEL):
        raise ValueError("unapproved_management_scope")
    entries = cfg.get("projects")
    if not isinstance(entries, list) or len(entries) != 3:
        raise ValueError("three_project_lanes_required")
    actual = set()
    allowed = {
        "ai": ("Katarina-AI", "public", "katarina-orchestrated-team.yml"),
        "freelance": ("Katarina-Freelance", "private", "freelance-source-ci.yml"),
        "web": ("Katarina-web", "public", "cloudflare-free-audit.yml"),
    }
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("invalid_project_lane")
        pid = item.get("id")
        if pid not in allowed or pid in actual:
            raise ValueError("duplicate_or_unknown_project")
        actual.add(pid)
        if (item.get("repository"), item.get("visibility"),
                item.get("workflow")) != allowed[pid]:
            raise ValueError("workflow_allowlist_violation")
        if item.get("branch") != "main":
            raise ValueError("only_main_branch_allowed")
        if (not REPO_NAME.fullmatch(item["repository"]) or
                not WORKFLOW.fullmatch(item["workflow"])):
            raise ValueError("invalid_repo_or_workflow")
    if actual != set(PROJECTS):
        raise ValueError("missing_project_lanes")
    return cfg


def make_plan(cfg: dict, scope: str, mode: str, commit: str,
              run_id: str, *, now: datetime | None = None) -> dict:
    if scope not in SCOPES or mode not in MODES:
        raise ValueError("invalid_scope_or_mode")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("github_commit_required")
    if not re.fullmatch(r"[0-9]{1,20}", run_id):
        raise ValueError("github_run_id_required")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("utc_aware_time_required")
    active = [p for p in cfg["projects"] if scope == "all" or p["id"] == scope]
    return signed({
        "version": RECEIPT_VERSION,
        "kind": "plan",
        "manifest_sha256": sha(cfg),
        "commit": commit,
        "run_id": run_id,
        "created_at_utc": moment.astimezone(timezone.utc).isoformat(),
        "scope": scope,
        "mode": mode,
        "max_parallel": MAX_PARALLEL,
        "retry_limit": 0,
        "dependency_graph": ["plan", "project_workers", "qa", "manager"],
        "project_lanes": [p["id"] for p in active],
        "projects": active,
        "git_writes_allowed": False,
        "applications_allowed": False,
        "web_deployment_allowed": False,
        "trading_allowed": False,
    })


def plan_matrix(plan: dict) -> dict:
    verify_receipt(plan)
    return {"include": [{"project": p["id"]} for p in plan["projects"]]}


def make_worker_report(plan: dict, project: str, operation: dict,
                       *, when: datetime | None = None) -> dict:
    verify_receipt(plan)
    if project not in plan["project_lanes"]:
        raise ValueError("unscheduled_project")
    if operation.get("status") not in (
        "HEALTH_OK", "CI_FAILED", "CI_NOT_COMPLETED", "DISPATCH_ACCEPTED",
        "BLOCKED_AUTH", "BLOCKED_NETWORK", "BLOCKED_CONFIG",
    ):
        raise ValueError("unsupported_result_status")
    entry = next(p for p in plan["projects"] if p["id"] == project)
    moment = when or datetime.now(timezone.utc)
    return signed({
        "version": RECEIPT_VERSION, "kind": "worker", "project": project,
        "repository": OWNER + "/" + entry["repository"],
        "workflow": entry["workflow"], "mode": plan["mode"],
        "run_id": plan["run_id"], "commit": plan["commit"],
        "plan_receipt_sha256": plan["receipt_sha256"],
        "status": operation["status"],
        "message": operation.get("message", ""),
        "observed_run_id": operation.get("observed_run_id"),
        "observed_conclusion": operation.get("observed_conclusion"),
        "dispatched_run_url": operation.get("dispatched_run_url"),
        "checked_at_utc": moment.astimezone(timezone.utc).isoformat(),
        "proven_completed_task": operation["status"] == "HEALTH_OK",
        "real_trading_authorized": False,
        "job_application_authorized": False,
        "production_write_authorized": False,
    })


def qa(plan: dict, reports: dict[str, dict]) -> dict:
    verify_receipt(plan)
    target = set(plan["project_lanes"])
    if set(reports) != target:
        raise ValueError("missing_or_extra_worker_receipts")
    individual = {}
    for project in plan["project_lanes"]:
        record = reports[project]
        d = verify_receipt(record)
        expected = next(p for p in plan["projects"] if p["id"] == project)
        if (d.get("kind") != "worker" or d.get("project") != project or
                d.get("repository") != OWNER+"/"+expected["repository"] or
                d.get("plan_receipt_sha256") != plan["receipt_sha256"] or
                d.get("run_id") != plan["run_id"] or
                d.get("commit") != plan["commit"] or
                d.get("workflow") != expected["workflow"] or
                d.get("mode") != plan["mode"] or
                d.get("version") != RECEIPT_VERSION or
                d.get("real_trading_authorized") is not False or
                d.get("job_application_authorized") is not False or
                d.get("production_write_authorized") is not False):
            raise ValueError("worker_receipt_cross_lane_or_tampering")
        individual[project] = {
            "status": d["status"], "worker_receipt_sha256": record["receipt_sha256"],
            "observed_conclusion": d.get("observed_conclusion"),
            "dispatched_run_url": d.get("dispatched_run_url"),
        }
    return signed({
        "version": RECEIPT_VERSION, "kind": "qa",
        "run_id": plan["run_id"], "commit": plan["commit"],
        "plan_receipt_sha256": plan["receipt_sha256"],
        "all_project_receipts_verified": True,
        "project_results": individual,
        "live_actions_blocked": True,
    })


def manager(plan: dict, qa_record: dict) -> dict:
    verify_receipt(plan)
    checked = verify_receipt(qa_record)
    if (checked.get("kind") != "qa" or
            checked.get("plan_receipt_sha256") != plan["receipt_sha256"] or
            checked.get("run_id") != plan["run_id"] or
            checked.get("commit") != plan["commit"] or
            checked.get("all_project_receipts_verified") is not True or
            checked.get("live_actions_blocked") is not True):
        raise ValueError("unapproved_qa_result")
    results = checked["project_results"]
    blocked = [key for key, item in results.items()
               if item["status"].startswith("BLOCKED")]
    failed = [key for key, item in results.items()
              if item["status"] == "CI_FAILED"]
    pending = [key for key, item in results.items()
               if item["status"] in ("DISPATCH_ACCEPTED", "CI_NOT_COMPLETED")]
    if failed:
        state = "ATTENTION_CI_FAILED"
    elif blocked:
        state = "PARTIALLY_BLOCKED"
    elif pending:
        state = "AWAITING_REMOTE_RESULTS"
    else:
        state = "ALL_TRACKS_AUDITED"
    return signed({
        "version": RECEIPT_VERSION, "kind": "manager",
        "commit": plan["commit"], "run_id": plan["run_id"],
        "mode": plan["mode"], "qa_receipt_sha256": qa_record["receipt_sha256"],
        "overall_status": state,
        "tracks": results,
        "blocked_projects": blocked, "failed_projects": failed,
        "pending_projects": pending,
        "next_priority": "RESOLVE_BLOCKERS" if blocked else
                         ("FIX_CI" if failed else "CONTINUE_PER_TRACK"),
        "repository_separation": True,
        "no_auto_application": True, "no_auto_deployment": True,
        "no_live_trading": True,
        "automatic_cross_repository_code_writes": False,
    })
