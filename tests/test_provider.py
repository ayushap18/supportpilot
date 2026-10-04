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
