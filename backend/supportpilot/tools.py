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
