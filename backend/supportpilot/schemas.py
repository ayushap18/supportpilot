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


class TicketPatch(Contract):
    expected_revision: int = Field(ge=1)
    subject: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=10, max_length=6000)
    product_version: Literal["v1", "v2"] | None = None
    account_id: str | None = Field(default=None, max_length=80)
    log: str | None = Field(default=None, max_length=12000)
    status: Literal["open", "in_progress", "waiting", "resolved"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    assignee: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def reject_null_required(self):
        for key in self.model_fields_set - {"account_id", "product_version", "assignee"}:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class NoteCreate(Contract):
    body: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def reject_blank(self):
        if not self.body.strip():
            raise ValueError("Note cannot be blank")
        return self


class Note(NoteCreate):
    id: str
    author_id: str
    created_at: datetime


class Ticket(TicketCreate):
    id: str
    workspace_id: str
    created_at: datetime
    status: Literal["open", "in_progress", "waiting", "resolved"] = "open"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    assignee: str | None = None
    revision: int = 1
    updated_at: datetime | None = None
    # Set by the GitHub webhook when the run's PR merges; awaiting customer confirmation.
    fix_merged_at: datetime | None = None


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
    ticket_revision: int = 1
    draft_revision: int = 1
    draft: Draft | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0
    mode: Literal["fixture", "live"] = "fixture"
    provider: str | None = None  # Live model provider; part of the autonomy bucket.
    # What earned autonomy would do with this draft; scored against the human verdict.
    shadow_decision: Literal["approve", "hold"] | None = None
    error: str | None = None


class ReviewCreate(Contract):
    draft_revision: int = Field(ge=1)
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1000)
    # Required, so a client that omits it is never counted as a human vote. ponytail:
    # self-declared, since the autopilot shares the human's token; a bot token would let the
    # server set it.
    reviewer_kind: Literal["human", "policy"]


class Review(ReviewCreate):
    id: str
    investigation_id: str
    reviewer_id: str
    created_at: datetime
