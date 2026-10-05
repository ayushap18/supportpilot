import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from supportpilot.config import Settings


def test_github_settings_optional_and_validated():
    base = {"_env_file": None}
    assert not Settings(**base).github_client_id
    assert Settings(**base, integration_encryption_key=Fernet.generate_key().decode())
    for callback in (
        "http://untrusted.example/api/github/callback",
        "https://example.com/api/github/callback?token=secret",
        "https://user:password@example.com/api/github/callback",
        "https://example.com/wrong-route",
    ):
        with pytest.raises(ValidationError):
            Settings(**base, github_redirect_uri=callback)
    with pytest.raises(ValidationError):
        Settings(**base, integration_encryption_key="invalid-key")
    assert Settings(**base, github_redirect_uri="https://example.com/api/github/callback")
