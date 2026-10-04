import re


def redact(text: str) -> str:
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}", r"\1[REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[REDACTED]", text)
    return re.sub(
        r"(?i)((?:api[_-]?key|password|secret|token)\s*[:=]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        text,
    )
