"""Bounded GitHub transport. Never follows URLs supplied by repository content."""

import asyncio
import json

import httpx
from fastapi import HTTPException


class GitHubClient:
    def __init__(self, token=""):
        self.token = token

    async def request(self, method, path, *, params=None, body=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("GitHub API path required")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        try:
            async with (
                asyncio.timeout(20),
                httpx.AsyncClient(timeout=20, follow_redirects=False) as client,
            ):
                async with client.stream(
                    method,
                    "https://api.github.com" + path,
                    headers=headers,
                    params=params,
                    json=body,
                ) as response:
                    if response.status_code >= 300:
                        status = 429 if response.status_code == 429 else 502
                        if response.status_code in (401, 403):
                            status = 403
                        if response.status_code == 404:
                            status = 404
                        raise HTTPException(
                            status, "GitHub request unavailable; check access or rate limits"
                        )
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 8_000_000:
                            raise HTTPException(
                                502, "GitHub response exceeds the snapshot size limit"
                            )
                    return json.loads(data), dict(response.headers)
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            raise HTTPException(502, "GitHub request failed; retry read operations later") from exc

    async def get(self, path, params=None):
        result, _ = await self.request("GET", path, params=params)
        return result


async def exchange_code(settings, code, verifier, redirect_uri=None):
    try:
        async with (
            asyncio.timeout(20),
            httpx.AsyncClient(timeout=20, follow_redirects=False) as client,
        ):
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret.get_secret_value(),
                    "redirect_uri": redirect_uri or settings.github_redirect_uri,
                    "code": code,
                    "code_verifier": verifier,
                },
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result.get("access_token"), str):
                raise ValueError("No token")
            return result
    except (httpx.HTTPError, ValueError, TimeoutError) as exc:
        raise HTTPException(502, "GitHub authorization failed") from exc
