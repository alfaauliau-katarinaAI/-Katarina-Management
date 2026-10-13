"""Entry point: scheduler, parallel worker, QA and manager."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .core import (
    load_manifest, make_plan, manager, plan_matrix, qa, verify_receipt,
)
from .github import process_lane

ROOT = Path(__file__).resolve().parents[1]


def store(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, sort_keys=True,
                               ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("plan", "worker", "finish"))
    parser.add_argument("--scope", choices=("all", "ai", "freelance", "web"),
                        default="all")
    parser.add_argument("--mode", choices=("audit", "dispatch"), default="audit")
    parser.add_argument("--project", choices=("ai", "freelance", "web"))
    parser.add_argument("--plan-file", type=Path, default=Path("out/plan.json"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    if args.phase == "plan":
        cfg = load_manifest(ROOT / "config/projects.json")
        plan = make_plan(cfg, args.scope, args.mode,
                         os.environ.get("GITHUB_SHA", ""),
                         os.environ.get("GITHUB_RUN_ID", ""))
        store(args.out / "plan.json", plan)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as stream:
                stream.write("matrix=" + json.dumps(
                    plan_matrix(plan), separators=(",", ":")) + "\n")
        print("MANAGEMENT_PLAN", args.scope, args.mode,
              "lanes", len(plan["project_lanes"]))
        return

    plan = json.loads(args.plan_file.read_text(encoding="utf-8"))
    verify_receipt(plan)
    if args.phase == "worker":
        if not args.project:
            raise ValueError("missing_worker_project")
        result = process_lane(
            plan, args.project,
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            private_read_token=os.environ.get("MANAGEMENT_REPO_READ_TOKEN", ""),
            dispatch_token=os.environ.get("MANAGEMENT_DISPATCH_TOKEN", ""))
        store(args.out / (args.project + ".json"), result)
        print("MANAGEMENT_WORKER", args.project, result["status"])
        return

    reports = {}
    for project in plan["project_lanes"]:
        path = args.out / (project + ".json")
        if not path.is_file():
            raise ValueError("missing_project_receipt:" + project)
        reports[project] = json.loads(path.read_text(encoding="utf-8"))
    qa_result = qa(plan, reports)
    store(args.out / "qa.json", qa_result)
    summary = manager(plan, qa_result)
    store(args.out / "manager.json", summary)
    print("MANAGEMENT_MANAGER", summary["overall_status"])
    lines = ["## Katarina Management — three independent lanes", "",
             "Mode: **{}**. Overall: **{}**.".format(
                 plan["mode"], summary["overall_status"]), "",
             "| Project | Latest check/dispatch |", "|---|---|"]
    for project, item in summary["tracks"].items():
        lines.append("| {} | {} |".format(project, item["status"]))
    lines += ["", "Dispatch accepted means **started, not completed**.",
              "No job applications, trading orders, deploys, merges or VPS changes."]
    (args.out / "SUMMARY.md").write_text("\n".join(lines) + "\n",
                                          encoding="utf-8")


if __name__ == "__main__":
    main()
