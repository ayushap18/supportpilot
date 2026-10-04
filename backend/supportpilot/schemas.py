from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TicketCreate(Contract):
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=6000)
    product_version: Literal["v1", "v2"] | None = None
    account_id: str | None = Field(default=None, max_length=80)
    log: str = Field(default="", max_length=12000)


class Ticket(TicketCreate):
    id: str
    workspace_id: str
    created_at: datetime


class Evidence(Contract):
    id: str
    kind: Literal["document", "tool"]
    title: str
    excerpt: str
    source_path: str | None = None
    product_version: str | None = None


class ToolCall(Contract):
    name: Literal["get_account_status", "get_service_health", "search_known_incidents"]
    arguments: "AccountArgs | HealthArgs | IncidentArgs"


class AccountArgs(Contract):
    account_id: str = Field(min_length=1, max_length=80)


class HealthArgs(Contract):
    service_name: Literal["webhooks", "api"]


class IncidentArgs(Contract):
    query: str = Field(min_length=1, max_length=200)
    product_version: Literal["v1", "v2"] | None = None


class ToolResult(Contract):
    name: str
    status: Literal["ok", "unknown", "denied", "error"]
    data: dict


class Draft(Contract):
    outcome: Literal["resolved", "needs_information", "escalate"]
    response: str = Field(min_length=1, max_length=8000)
    missing_information: list[str]
    evidence_ids: list[str]

    @model_validator(mode="after")
    def require_support(self):
        if self.outcome == "resolved" and not self.evidence_ids:
            raise ValueError("A resolved draft requires evidence")
        if self.outcome == "needs_information" and not self.missing_information:
            raise ValueError("Clarification requires a concrete missing detail")
        return self


class ModelStep(Contract):
    summary: str
    tool_calls: list[ToolCall]
    draft: Draft | None


class TraceEvent(Contract):
    stage: str
    summary: str
    duration_ms: float = 0
    tool_result: ToolResult | None = None
    tool_arguments: dict | None = None


class Usage(Contract):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None
    model_rounds: int = 0
    tool_calls: int = 0


class Investigation(Contract):
    id: str
    ticket_id: str
    workspace_id: str
    state: Literal["queued", "running", "awaiting_review", "failed"]
    created_at: datetime
    draft_revision: int = 1
    draft: Draft | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0
    mode: Literal["fixture", "live"] = "fixture"
    error: str | None = None


class ReviewCreate(Contract):
    draft_revision: int = Field(ge=1)
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1000)


class Review(ReviewCreate):
    id: str
    investigation_id: str
    reviewer_id: str
    created_at: datetime
