from supportpilot.schemas import AccountArgs, Draft, ModelStep, ToolCall, Usage
from test_workflow import run_ticket


def test_model_cannot_switch_the_ticket_account(client, headers, ticket_input):
    async def malicious_plan(ticket, evidence, results, **kwargs):
        if not results:
            return ModelStep(
                summary="Try a different account",
                draft=None,
                tool_calls=[
                    ToolCall(
                        name="get_account_status", arguments=AccountArgs(account_id="acct_pro")
                    )
                ],
            ), Usage(model_rounds=1)
        assert results[0].status == "denied"
        assert "requests_per_minute" not in results[0].data
        return ModelStep(
            summary="Escalate",
            tool_calls=[],
            draft=Draft(
                outcome="escalate",
                response="The requested account could not be checked.",
                missing_information=[],
                evidence_ids=[],
            ),
        ), Usage(model_rounds=1)

    client.app.state.provider.step = malicious_plan
    result = run_ticket(client, headers, ticket_input)
    assert result["draft"]["outcome"] == "escalate"
    tool = next(event for event in result["trace"] if event["stage"] == "tool")
    assert tool["tool_result"]["status"] == "denied"
