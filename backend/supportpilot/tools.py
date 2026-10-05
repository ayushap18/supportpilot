import json

from pydantic import ValidationError

from supportpilot.schemas import AccountArgs, HealthArgs, IncidentArgs, ToolResult

ARGUMENTS = {
    "get_account_status": AccountArgs,
    "get_service_health": HealthArgs,
    "search_known_incidents": IncidentArgs,
}


class Tools:
    """Allowlisted read-only synthetic integrations. Identity is always server supplied."""

    def __init__(self, data_dir):
        self.fixtures = json.loads((data_dir / "tools.json").read_text())
        self.errors = {}

    async def execute(self, call, workspace):
        try:
            arguments = ARGUMENTS[call.name].model_validate(call.arguments.model_dump())
        except (ValidationError, KeyError):
            return ToolResult(name=call.name, status="error", data={"message": "Invalid arguments"})
        if call.name in self.errors:
            return ToolResult(name=call.name, status="error", data={"message": "Tool unavailable"})
        if call.name == "get_account_status":
            account = next(
                (item for item in self.fixtures["accounts"] if item["id"] == arguments.account_id),
                None,
            )
            if account is None or account["workspace_id"] != workspace:
                return ToolResult(
                    name=call.name, status="unknown", data={"message": "Account not found"}
                )
            data = {key: value for key, value in account.items() if key != "workspace_id"}
        elif call.name == "get_service_health":
            data = self.fixtures["health"][arguments.service_name]
        else:
            matches = [
                item
                for item in self.fixtures["incidents"]
                if item["workspace_id"] == workspace
                and (
                    arguments.product_version is None
                    or item["product_version"] == arguments.product_version
                )
                and any(
                    word in (item["summary"] + " " + item["service"]).lower()
                    for word in arguments.query.lower().split()
                )
            ]
            data = {
                "incidents": [
                    {key: value for key, value in item.items() if key != "workspace_id"}
                    for item in matches[:5]
                ]
            }
        if len(json.dumps(data)) > 5000:
            return ToolResult(
                name=call.name, status="error", data={"message": "Tool output exceeded budget"}
            )
        return ToolResult(name=call.name, status="ok", data=data)


class GitHubTools:
    """Real, read-only integrations from the workspace's connected GitHub repositories.

    Service health = latest CI/deployment workflow results on the default branch.
    Known incidents = open issues labelled `incident`. Account lookups are not connected.
    """

    def __init__(self, database, settings):
        self.database = database
        self.settings = settings

    async def execute(self, call, workspace):
        from sqlalchemy import select

        from supportpilot.github import workspace_github
        from supportpilot.github_storage import GitHubRepositoryRow

        try:
            arguments = ARGUMENTS[call.name].model_validate(call.arguments.model_dump())
        except (ValidationError, KeyError):
            return ToolResult(name=call.name, status="error", data={"message": "Invalid arguments"})
        if call.name == "get_account_status":
            return ToolResult(
                name=call.name,
                status="error",
                data={"message": "Account lookups are not connected to a real system"},
            )
        github = workspace_github(self.database, self.settings, workspace)
        with self.database.session() as session:
            repos = [
                r.payload
                for r in session.scalars(
                    select(GitHubRepositoryRow).where(GitHubRepositoryRow.workspace_id == workspace)
                )
            ][:3]
        if github is None or not repos:
            return ToolResult(
                name=call.name,
                status="unknown",
                data={"message": "No GitHub repository is connected to this workspace"},
            )
        try:
            if call.name == "get_service_health":
                workflows = []
                for repo in repos:
                    runs = await github.get(
                        f"/repos/{repo['full_name']}/actions/runs",
                        {"branch": repo.get("default_branch") or "main", "per_page": 20},
                    )
                    latest = {}
                    for run in runs.get("workflow_runs", []):  # Newest first.
                        latest.setdefault(run.get("name"), run)
                    workflows += [
                        {
                            "repository": repo["full_name"],
                            "workflow": name,
                            "status": run.get("status"),
                            "conclusion": run.get("conclusion"),
                            "updated_at": run.get("updated_at"),
                            "url": run.get("html_url"),
                        }
                        for name, run in latest.items()
                    ]
                failing = [w for w in workflows if w["conclusion"] in ("failure", "timed_out")]
                data = {
                    "source": "github_actions",
                    "status": "unknown"
                    if not workflows
                    else "degraded"
                    if failing
                    else "operational",
                    "workflows": workflows[:10],
                }
            else:
                words = [w for w in arguments.query.lower().split() if len(w) > 2]
                incidents = []
                for repo in repos:
                    issues = await github.get(
                        f"/repos/{repo['full_name']}/issues",
                        {"labels": "incident", "state": "open", "per_page": 30},
                    )
                    incidents += [
                        {
                            "repository": repo["full_name"],
                            "number": i["number"],
                            "title": i["title"][:200],
                            "status": "active",
                            "updated_at": i.get("updated_at"),
                            "url": i.get("html_url"),
                        }
                        for i in issues
                        if "pull_request" not in i
                        and (
                            not words
                            or any(
                                w in (i["title"] + " " + (i.get("body") or "")).lower()
                                for w in words
                            )
                        )
                    ]
                data = {"source": "github_issues", "incidents": incidents[:5]}
        except Exception:  # GitHub transport errors become an honest tool failure.
            return ToolResult(
                name=call.name, status="error", data={"message": "GitHub request failed"}
            )
        if len(json.dumps(data)) > 5000:
            return ToolResult(
                name=call.name, status="error", data={"message": "Tool output exceeded budget"}
            )
        return ToolResult(name=call.name, status="ok", data=data)
