import asyncio
import json
import time

from supportpilot.schemas import Evidence, TraceEvent


async def investigate(
    ticket, investigation, retrieval, provider, settings, tools=None, allow_tools=True
):
    started = time.monotonic()
    investigation.state = "running"
    results = []
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
            for _ in range(settings.max_rounds):
                stage_started = time.monotonic()
                step, usage = await provider.step(
                    ticket, evidence, results, allow_tools=allow_tools
                )
                investigation.usage.model_rounds += 1
                investigation.usage.input_tokens += usage.input_tokens
                investigation.usage.output_tokens += usage.output_tokens
                investigation.trace.append(
                    TraceEvent(
                        stage="model",
                        summary=step.summary,
                        duration_ms=(time.monotonic() - stage_started) * 1000,
                    )
                )
                if step.tool_calls:
                    if not allow_tools or tools is None or step.draft is not None:
                        raise ValueError("Invalid tool plan")
                    for call in step.tool_calls:
                        if investigation.usage.tool_calls >= settings.max_tool_calls:
                            raise ValueError("Tool call budget exceeded")
                        investigation.usage.tool_calls += 1
                        tool_started = time.monotonic()
                        async with asyncio.timeout(min(5, settings.timeout_seconds)):
                            result = await tools.execute(call, ticket.workspace_id)
                        results.append(result)
                        evidence.append(
                            Evidence(
                                id=f"tool:{investigation.usage.tool_calls}:{call.name}",
                                kind="tool",
                                title=call.name,
                                excerpt=json.dumps(result.model_dump()),
                            )
                        )
                        investigation.trace.append(
                            TraceEvent(
                                stage="tool",
                                summary=f"{call.name}: {result.status}",
                                duration_ms=(time.monotonic() - tool_started) * 1000,
                                tool_result=result,
                            )
                        )
                    continue
                if step.draft is None:
                    raise ValueError("No draft returned")
                known = {item.id for item in evidence}
                if not set(step.draft.evidence_ids) <= known:
                    raise ValueError("Draft references unavailable evidence")
                if step.draft.outcome == "resolved" and any(
                    item.status != "ok" for item in results
                ):
                    raise ValueError("A failed tool cannot support a resolution")
                investigation.draft = step.draft
                investigation.state = "awaiting_review"
                investigation.trace.append(
                    TraceEvent(
                        stage="validate",
                        summary="Draft schema and citation IDs validated. Human review required.",
                    )
                )
                break
            else:
                raise ValueError("Model round budget exceeded")
    except TimeoutError:
        investigation.state, investigation.error = "failed", "Investigation time budget exceeded"
    except Exception:
        investigation.state, investigation.error = (
            "failed",
            "Investigation failed validation or a dependency was unavailable",
        )
    if (
        settings.mode == "live"
        and settings.pricing_date
        and (
            settings.input_usd_per_million is not None
            and settings.output_usd_per_million is not None
        )
    ):
        # Generation only: embedding charges are excluded.
        investigation.usage.estimated_cost_usd = (
            investigation.usage.input_tokens * settings.input_usd_per_million
            + investigation.usage.output_tokens * settings.output_usd_per_million
        ) / 1_000_000
    investigation.latency_ms = (time.monotonic() - started) * 1000
    return investigation
