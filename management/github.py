"""Audited GitHub API client: GET status, or explicit allowlisted dispatch.

Never prints provider error bodies, tokens, or unbounded remote data. No code
writes, branch mutation or arbitrary URLs. Auth failures remain BLOCKED.
"""
from __future__ import annotations

import json
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core import OWNER, make_worker_report, verify_receipt

MAX_BODY = 250_000


class SafeGitHubError(Exception):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


class Client:
    def __init__(self, token: str = "", transport: Callable = urlopen):
        self.token = token
        self.transport = transport

    def call(self, endpoint: str, *, method: str = "GET", body: dict | None = None):
        if (not endpoint.startswith("/repos/" + OWNER + "/") or
                not re.fullmatch(r"/[A-Za-z0-9_.\-/%?=&]+", endpoint)):
            raise ValueError("untrusted_api_endpoint")
        if method not in ("GET", "POST"):
            raise ValueError("unsupported_api_method")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Katarina-Management-Read-Only-By-Default",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        data = json.dumps(body).encode() if body is not None else None
        if method == "POST":
            headers["Content-Type"] = "application/json"
        req = Request("https://api.github.com" + endpoint, headers=headers,
                      method=method, data=data)
        try:
            with self.transport(req, timeout=12) as response:
                raw = response.read(MAX_BODY + 1)
                code = getattr(response, "status", 200)
        except HTTPError as exc:
            if exc.code in (401, 403, 404):
                raise SafeGitHubError("BLOCKED_AUTH") from None
            raise SafeGitHubError("BLOCKED_NETWORK") from None
        except (URLError, TimeoutError, OSError):
            raise SafeGitHubError("BLOCKED_NETWORK") from None
        if len(raw) > MAX_BODY:
            raise SafeGitHubError("BLOCKED_CONFIG")
        if not raw.strip():
            return code, None
        try:
            return code, json.loads(raw)
        except (ValueError, TypeError):
            raise SafeGitHubError("BLOCKED_CONFIG") from None


def process_lane(plan: dict, project: str, *, github_token: str = "",
                 private_read_token: str = "", dispatch_token: str = "",
                 transport: Callable = urlopen) -> dict:
    """Every run produces a receipt. No auth means BLOCKED, never PASS."""
    verify_receipt(plan)
    if project not in plan["project_lanes"]:
        raise ValueError("unscheduled_project")
    target = next(x for x in plan["projects"] if x["id"] == project)
    repo = target["repository"]
    path = "/repos/" + OWNER + "/" + repo
    workflow = target["workflow"]
    mode = plan["mode"]

    if mode == "audit":
        token = private_read_token if target["visibility"] == "private" else (
            private_read_token or github_token)
        if target["visibility"] == "private" and not token:
            operation = {"status": "BLOCKED_AUTH",
                         "message": "PRIVATE_READ_TOKEN_NOT_CONFIGURED"}
            return make_worker_report(plan, project, operation)
        client = Client(token, transport)
        try:
            code, info = client.call(
                path + "/actions/workflows/" + workflow + "/runs?per_page=1")
            if code != 200 or not isinstance(info, dict):
                raise SafeGitHubError("BLOCKED_CONFIG")
            runs = info.get("workflow_runs", [])
            if not isinstance(runs, list):
                raise SafeGitHubError("BLOCKED_CONFIG")
            if not runs:
                operation = {"status": "CI_NOT_COMPLETED",
                             "message": "NO_VERIFIABLE_WORKFLOW_RUN"}
            else:
                run = runs[0]
                conclusion = run.get("conclusion")
                status = run.get("status")
                if status != "completed":
                    result = "CI_NOT_COMPLETED"
                elif conclusion == "success":
                    result = "HEALTH_OK"
                else:
                    result = "CI_FAILED"
                operation = {"status": result,
                             "message": "REMOTE_WORKFLOW_STATUS_OBSERVED",
                             "observed_run_id": run.get("id"),
                             "observed_conclusion": conclusion}
        except SafeGitHubError as error:
            operation = {"status": error.category,
                         "message": "GITHUB_API_NOT_VERIFIED"}
    else:
        if not dispatch_token:
            operation = {"status": "BLOCKED_AUTH",
                         "message": "CROSS_REPO_DISPATCH_TOKEN_NOT_CONFIGURED"}
            return make_worker_report(plan, project, operation)
        client = Client(dispatch_token, transport)
        try:
            code, meta = client.call(path + "/actions/workflows/" + workflow)
            if (code != 200 or not isinstance(meta, dict) or
                    meta.get("state") != "active" or
                    str(meta.get("path", "")).split("/")[-1] != workflow):
                raise SafeGitHubError("BLOCKED_CONFIG")
            result_code, result = client.call(
                path + "/actions/workflows/" + workflow + "/dispatches",
                method="POST", body={"ref": "main",
                                     "inputs": {}, "return_run_details": True})
            if result_code not in (200, 204):
                raise SafeGitHubError("BLOCKED_CONFIG")
            run_url = (result or {}).get("html_url") if isinstance(result, dict) else None
            if run_url and not run_url.startswith(
                    "https://github.com/" + OWNER + "/" + repo + "/actions/runs/"):
                run_url = None
            operation = {"status": "DISPATCH_ACCEPTED",
                         "message": "REMOTE_WORKFLOW_STARTED_NOT_FINISHED",
                         "dispatched_run_url": run_url}
        except SafeGitHubError as error:
            operation = {"status": error.category,
                         "message": "CROSS_REPO_DISPATCH_UNVERIFIED"}
    return make_worker_report(plan, project, operation)
