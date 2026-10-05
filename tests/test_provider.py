import asyncio
from types import SimpleNamespace

from supportpilot.provider import Provider
from supportpilot.schemas import Draft, ModelStep, Ticket, Usage


def test_live_adapter_structured_output_contract(settings):
    async def run():
        settings.mode = "live"
        provider = Provider(settings)
        observed = {}

        async def parse(**kwargs):
            observed.update(kwargs)
            return SimpleNamespace(
                status="completed",
                output_parsed=ModelStep(
                    summary="Request missing details",
                    tool_calls=[],
                    draft=Draft(
                        outcome="needs_information",
                        response="Which API version?",
                        missing_information=["API version"],
                        evidence_ids=[],
                    ),
                ),
                usage=SimpleNamespace(input_tokens=100, output_tokens=20),
            )

        provider.client.responses.parse = parse
        ticket = Ticket(
            id="test",
            workspace_id="demo",
            created_at="2026-10-04T00:00:00Z",
            subject="API error",
            description="Our authentication request fails.",
        )
        result, usage = await provider.step(ticket, [], [])
        assert result.draft.outcome == "needs_information"
        assert usage == Usage(input_tokens=100, output_tokens=20, model_rounds=1)
        assert observed["text_format"] is ModelStep
        assert observed["store"] is False
        assert observed["max_output_tokens"] == settings.max_output_tokens
        await provider.close()

    asyncio.run(run())


def test_claude_adapter_structured_output_fallbacks_and_refusal(settings):
    import pytest

    async def run():
        settings.mode = "live"
        settings.llm_provider = "anthropic"
        provider = Provider(settings)
        assert provider.client is None  # No OpenAI key: lexical retrieval, no OpenAI calls.
        assert provider.embedding_signature == "fixture-lexical-v1"
        observed = {}
        step = ModelStep(summary="Escalate", tool_calls=[], draft=None)
        reply = SimpleNamespace(
            stop_reason="end_turn",
            parsed_output=step,
            usage=SimpleNamespace(input_tokens=300, output_tokens=40),
        )

        async def parse(**kwargs):
            observed.update(kwargs)
            return reply

        provider.claude.beta.messages.parse = parse
        ticket = Ticket(
            id="t",
            workspace_id="demo",
            created_at="2026-10-04T00:00:00Z",
            subject="Refund please",
            description="Refund my last invoice.",
        )
        result, usage = await provider.step(ticket, [], [])
        assert result is step and (usage.input_tokens, usage.output_tokens) == (300, 40)
        assert observed["model"] == "claude-opus-5-5" and observed["output_format"] is ModelStep
        assert observed["output_config"] == {"effort": "medium"}
        assert observed["fallbacks"] == "default"
        assert observed["betas"] == ["server-side-fallback-2026-07-01"]
        assert "thinking" not in observed and "temperature" not in observed
        assert "Refund my last invoice." in observed["messages"][0]["content"]

        reply.stop_reason = "refusal"
        with pytest.raises(ValueError, match="declined"):
            await provider.step(ticket, [], [])
        reply.stop_reason, reply.parsed_output = "max_tokens", None
        with pytest.raises(ValueError, match="complete"):
            await provider.step(ticket, [], [])
        await provider.close()

    asyncio.run(run())


def test_live_anthropic_mode_does_not_require_openai_key(settings):
    from supportpilot.config import Settings

    Settings(_env_file=None, mode="live", llm_provider="anthropic")
    import pytest

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, mode="live")
