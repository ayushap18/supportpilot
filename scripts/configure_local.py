"""Generate local credentials without printing them or overwriting an existing .env."""

import json
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
token = secrets.token_urlsafe(32)
identity = [{"token": token, "workspace_id": "demo", "reviewer_id": "local-reviewer"}]
content = (
    (root / ".env.example")
    .read_text()
    .replace(
        "SUPPORTPILOT_API_TOKENS_JSON=[]", "SUPPORTPILOT_API_TOKENS_JSON=" + json.dumps(identity)
    )
)
with (root / ".env").open("x") as target:
    target.write(content)
(root / ".env").chmod(0o600)
print("Created .env with a private demo workspace token. Open it locally to connect the UI.")
