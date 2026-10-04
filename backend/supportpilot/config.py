import json
import math
import os
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(os.environ.get("SUPPORTPILOT_ROOT", Path(__file__).resolve().parents[2]))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SUPPORTPILOT_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///.state/supportpilot.db"
    api_tokens_json: SecretStr = SecretStr("[]")
    mode: Literal["fixture", "live"] = "fixture"
    openai_api_key: SecretStr = SecretStr("")
    model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    data_dir: Path = ROOT / "data/relaydesk"
    frontend_dir: Path = ROOT / "frontend/dist"
    max_rounds: int = 3
    max_tool_calls: int = 5
    timeout_seconds: float = Field(default=45, gt=0, le=45)
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
        if self.mode == "live" and not self.openai_api_key.get_secret_value():
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
