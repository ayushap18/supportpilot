import json
import math
import os
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(os.environ.get("SUPPORTPILOT_ROOT", Path(__file__).resolve().parents[2]))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SUPPORTPILOT_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///.state/supportpilot.db"
    api_tokens_json: SecretStr = SecretStr("[]")
    mode: Literal["fixture", "live"] = "fixture"
    openai_api_key: SecretStr = SecretStr("")
    # Live investigation model provider. Anthropic has no embeddings API, so retrieval uses
    # OpenAI embeddings when an OpenAI key is set and the lexical index otherwise.
    llm_provider: Literal["openai", "anthropic", "cli"] = "openai"
    # Keyless live mode: investigations run through your logged-in local CLI (subscription).
    cli_agent: Literal["claude_code", "codex", "antigravity"] = "claude_code"
    # Where investigation tools read from. None = synthetic in fixture mode, off in live mode.
    integrations: Literal["synthetic", "github", "off"] | None = None
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    github_redirect_uri: str = "http://127.0.0.1:8000/api/github/callback"
    # OAuth App callback for "Sign in with GitHub" (register a parent path such as .../api).
    github_login_redirect_uri: str = "http://127.0.0.1:8000/api/auth/github/callback"
    # GitHub issues carrying this label become tickets (on sync, and via the webhook).
    github_support_label: str = "support"
    # Shared secret for POST /api/github/webhook (issues and push events).
    github_webhook_secret: SecretStr = SecretStr("")
    # Slack incoming webhook for review-ready drafts and finished agent runs (optional).
    slack_webhook_url: SecretStr = SecretStr("")
    # Server-wide personal access token; skips OAuth for single-team local installs.
    github_token: SecretStr = SecretStr("")
    integration_encryption_key: SecretStr = SecretStr("")
    model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    data_dir: Path = ROOT / "data/relaydesk"
    frontend_dir: Path = ROOT / "frontend/dist"
    max_rounds: int = 3
    max_tool_calls: int = 5
    # Earned autonomy: workspaces (opt-in, none by default) where autopilot approves only
    # kinds of drafts with at least this many human reviews and this Wilson lower bound.
    autonomy_workspaces: list[str] = []
    autonomy_min_n: int = Field(default=20, ge=1)
    autonomy_min_lb: float = Field(default=0.9, gt=0, le=1)
    # Workspaces (opt-in, none by default) where a merged fix PR also resolves its ticket.
    resolve_on_merge_workspaces: list[str] = []
    # Whole-investigation budget. Local CLI providers need more than API calls (~10 s per step).
    timeout_seconds: float = Field(default=45, gt=0, le=600)
    max_output_tokens: int = Field(default=1800, ge=128, le=1800)
    max_input_chars: int = Field(default=40000, ge=1000, le=40000)
    max_investigations_per_hour: int = Field(default=30, ge=1, le=1000)
    retention_days: int = Field(default=30, ge=1, le=365)
    input_usd_per_million: float | None = None
    output_usd_per_million: float | None = None
    embedding_usd_per_million: float | None = None
    pricing_date: str | None = None

    @model_validator(mode="after")
    def validate_settings(self):
        if self.integration_encryption_key.get_secret_value():
            try:
                Fernet(self.integration_encryption_key.get_secret_value().encode())
            except (ValueError, TypeError) as exc:
                raise ValueError("Integration encryption key must be a valid Fernet key") from exc
        callback = urlparse(self.github_redirect_uri)
        if (
            callback.scheme not in {"https", "http"}
            or not callback.hostname
            or callback.username
            or callback.password
            or callback.fragment
            or callback.query
            or callback.path != "/api/github/callback"
            or (
                callback.scheme == "http"
                and callback.hostname not in {"localhost", "127.0.0.1", "::1"}
            )
        ):
            raise ValueError(
                "GitHub callback must use HTTPS (or local HTTP) at /api/github/callback"
            )
        if self.integrations is None:
            self.integrations = "synthetic" if self.mode == "fixture" else "off"
        if self.mode == "live" and self.integrations == "synthetic":
            raise ValueError(
                "Live mode cannot use synthetic integrations; set SUPPORTPILOT_INTEGRATIONS "
                "to github or off"
            )
        slack = self.slack_webhook_url.get_secret_value()
        if slack and not slack.startswith("https://hooks.slack.com/"):
            raise ValueError("Slack webhook URL must start with https://hooks.slack.com/")
        login = urlparse(self.github_login_redirect_uri)
        if login.scheme not in {"https", "http"} or login.path != "/api/auth/github/callback":
            raise ValueError("GitHub sign-in callback must end with /api/auth/github/callback")
        tokens = json.loads(self.api_tokens_json.get_secret_value())
        if not isinstance(tokens, list):
            raise ValueError("API tokens must be a JSON array")
        for entry in tokens:
            if (
                not isinstance(entry, dict)
                or not {"token", "workspace_id", "reviewer_id"} <= set(entry)
                or set(entry) - {"token", "workspace_id", "reviewer_id", "role"}
            ):
                raise ValueError("Each token needs token, workspace_id, and reviewer_id")
            if entry.get("role", "admin") not in {"admin", "agent"}:
                raise ValueError("Role must be admin or agent")
            if not all(
                isinstance(entry[key], str) for key in ("token", "workspace_id", "reviewer_id")
            ):
                raise ValueError("Token and identities must be strings")
            if len(entry["token"]) < 24 or not entry["workspace_id"] or not entry["reviewer_id"]:
                raise ValueError("Tokens need at least 24 characters and non-empty identities")
        if (
            self.mode == "live"
            and self.llm_provider == "openai"
            and not self.openai_api_key.get_secret_value()
        ):
            raise ValueError("Live mode requires SUPPORTPILOT_OPENAI_API_KEY")
        if self.max_rounds < 1 or self.max_rounds > 3 or not 1 <= self.max_tool_calls <= 5:
            raise ValueError("Budgets exceed the supported workflow bounds")
        if self.timeout_seconds <= 0 or self.max_investigations_per_hour < 1:
            raise ValueError("Timeout and hourly limit must be positive")
        for price in (
            self.input_usd_per_million,
            self.output_usd_per_million,
            self.embedding_usd_per_million,
        ):
            if price is not None and (not math.isfinite(price) or price < 0):
                raise ValueError("Pricing must be finite and non-negative")
        if self.pricing_date:
            date.fromisoformat(self.pricing_date)
        return self

    def identities(self) -> list[dict[str, str]]:
        return [
            {"role": "admin", **entry}
            for entry in json.loads(self.api_tokens_json.get_secret_value())
        ]
