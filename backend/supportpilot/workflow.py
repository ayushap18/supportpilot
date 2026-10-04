import asyncio
import time

from supportpilot.schemas import TraceEvent


async def investigate(ticket, investigation, retrieval, provider, settings, allow_tools=False):
    started = time.monotonic()
    investigation.state = "running"
    try:
        async with asyncio.timeout(settings.timeout_seconds):
            evidence = await retrieval.search(
                ticket.subject + " " + ticket.description + " " + ticket.log,
                ticket.workspace_id,
                ticket.product_version,
            )
            investigation.evidence = evidence
            investigation.trace.append(
                TraceEvent(
                    stage="retrieve",
                    summary=f"Retrieved {len(evidence)} version-filtered sources.",
                    duration_ms=(time.monotonic() - started) * 1000,
                )
            )
            step, usage = await provider.step(ticket, evidence, [], allow_tools=False)
            investigation.usage = usage
            if step.draft is None or step.tool_calls:
                raise ValueError("A baseline run must return a draft")
            known = {item.id for item in evidence}
            if not set(step.draft.evidence_ids) <= known:
                raise ValueError("Draft references unavailable evidence")
            investigation.draft = step.draft
            investigation.state = "awaiting_review"
            investigation.trace.append(TraceEvent(stage="draft", summary=step.summary))
    except TimeoutError:
        investigation.state, investigation.error = "failed", "Investigation time budget exceeded"
    except Exception:
        investigation.state, investigation.error = (
            "failed",
            "Investigation failed validation or a dependency was unavailable",
        )
    investigation.latency_ms = (time.monotonic() - started) * 1000
    return investigation
