import json
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


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
    timeout_seconds: float = 45
    max_output_tokens: int = 1800
    max_input_chars: int = 40000
    max_investigations_per_hour: int = 30
    retention_days: int = 30
    input_usd_per_million: float | None = None
    output_usd_per_million: float | None = None
    pricing_date: str | None = None

    @model_validator(mode="after")
    def validate_settings(self):
        tokens = json.loads(self.api_tokens_json.get_secret_value())
        if not isinstance(tokens, list):
            raise ValueError("API tokens must be a JSON array")
        for entry in tokens:
            if set(entry) != {"token", "workspace_id", "reviewer_id"}:
                raise ValueError("Each token needs token, workspace_id, and reviewer_id")
            if len(entry["token"]) < 24 or not entry["workspace_id"] or not entry["reviewer_id"]:
                raise ValueError("Tokens need at least 24 characters and non-empty identities")
        if self.mode == "live" and not self.openai_api_key.get_secret_value():
            raise ValueError("Live mode requires SUPPORTPILOT_OPENAI_API_KEY")
        if self.max_rounds < 1 or self.max_rounds > 3 or not 1 <= self.max_tool_calls <= 5:
            raise ValueError("Budgets exceed the supported workflow bounds")
        if self.timeout_seconds <= 0 or self.max_investigations_per_hour < 1:
            raise ValueError("Timeout and hourly limit must be positive")
        return self

    def identities(self) -> list[dict[str, str]]:
        return json.loads(self.api_tokens_json.get_secret_value())
