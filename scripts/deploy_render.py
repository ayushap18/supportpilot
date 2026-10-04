"""Trigger the tested commit without exposing the deploy hook in command output."""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def hook_url(hook: str, commit: str) -> str:
    parsed = urllib.parse.urlsplit(hook)
    if parsed.scheme != "https" or parsed.hostname != "api.render.com":
        raise ValueError("Expected an HTTPS api.render.com deploy hook")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Expected a full tested commit SHA")
    query = dict(urllib.parse.parse_qsl(parsed.query))
    query["ref"] = commit
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))


def main():
    hook = os.environ.get("RENDER_DEPLOY_HOOK_URL", "")
    if not hook:
        print("Render deployment skipped: configure RENDER_DEPLOY_HOOK_URL in repository secrets.")
        return
    try:
        url = hook_url(hook, os.environ["TESTED_COMMIT"])
        request = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            payload = json.loads(response.read())
        print(
            json.dumps(
                {
                    "status": status,
                    "deploy_id": payload.get("deploy", {}).get("id"),
                    "message": "Deployment requested; confirm completion in Render.",
                }
            )
        )
    except (ValueError, KeyError, urllib.error.URLError):
        print(
            "Render deployment request failed. Verify the hook and service configuration.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
