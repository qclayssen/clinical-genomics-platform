"""Tests for the Azure AI Foundry and AWS Bedrock LLM backends.

No real network/cloud calls: `AzureFoundryBackend` is exercised with a mocked
`openai.AzureOpenAI` client, `BedrockBackend` with a mocked boto3
`bedrock-runtime` client. This mirrors how the existing OpenAI/Anthropic
backends would be tested (they aren't, today) and keeps CI offline.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_AI_REPORT_DIR = Path(__file__).resolve().parents[1] / "ai-report"
if str(_AI_REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_REPORT_DIR))

from agent.llm import AzureFoundryBackend, BedrockBackend, Message, ToolCall, create_backend  # noqa: E402

# ═══ Azure AI Foundry ═══════════════════════════════════════════════════════


def test_azure_foundry_not_available_without_config(monkeypatch):
    monkeypatch.delenv("AZURE_AI_FOUNDRY_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_AI_FOUNDRY_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_AI_FOUNDRY_DEPLOYMENT", raising=False)
    backend = AzureFoundryBackend()
    assert backend.is_available() is False


def test_azure_foundry_available_with_full_config():
    backend = AzureFoundryBackend(
        endpoint="https://example.openai.azure.com",
        api_key="fake-key",
        deployment="gpt-4o-mini-deployment",
    )
    assert backend.is_available() is True
    assert backend.model_id == "azure_foundry/gpt-4o-mini-deployment"


def test_azure_foundry_generate_raises_without_config():
    # A fake `openai` module stands in so the missing-config ValueError (not
    # an unrelated "package not installed" ImportError) is what's asserted —
    # this environment may or may not have `openai` installed either way.
    backend = AzureFoundryBackend(endpoint="", api_key="", deployment="")
    with patch.dict(sys.modules, {"openai": MagicMock()}):
        try:
            backend.generate([Message(role="user", content="hi")])
            assert False, "expected ValueError"
        except ValueError as e:
            assert "AZURE_AI_FOUNDRY" in str(e)


def test_azure_foundry_generate_parses_tool_call_response():
    fake_tool_call = MagicMock()
    fake_tool_call.function.name = "query_clinvar"
    fake_tool_call.function.arguments = '{"chrom": "chr20", "pos": 1}'
    fake_tool_call.id = "call_1"

    fake_message = MagicMock(content=None, tool_calls=[fake_tool_call])
    fake_choice = MagicMock(message=fake_message, finish_reason="tool_calls")
    fake_response = MagicMock(choices=[fake_choice])
    fake_response.usage.prompt_tokens = 10
    fake_response.usage.completion_tokens = 5

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    fake_openai_module = MagicMock()
    fake_openai_module.AzureOpenAI.return_value = fake_client
    fake_openai_module.APIConnectionError = type("APIConnectionError", (Exception,), {})
    fake_openai_module.AuthenticationError = type("AuthenticationError", (Exception,), {})
    fake_openai_module.APIError = type("APIError", (Exception,), {})

    backend = AzureFoundryBackend(
        endpoint="https://example.openai.azure.com", api_key="fake-key", deployment="dep"
    )
    with patch.dict(sys.modules, {"openai": fake_openai_module}):
        response = backend.generate([Message(role="user", content="interpret this variant")])

    assert response.has_tool_calls
    assert response.tool_calls[0].name == "query_clinvar"
    assert response.tool_calls[0].arguments == {"chrom": "chr20", "pos": 1}
    assert response.stop_reason == "tool_use"
    assert response.usage == {"input_tokens": 10, "output_tokens": 5}
    fake_client.chat.completions.create.assert_called_once()
    call_kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "dep"


# ═══ AWS Bedrock ═════════════════════════════════════════════════════════════


def test_bedrock_defaults_and_model_id():
    backend = BedrockBackend()
    assert backend.model_id.startswith("bedrock/anthropic.claude")


def test_bedrock_generate_parses_tool_use_response():
    fake_response = {
        "output": {
            "message": {
                "content": [
                    {"text": "Looking this up."},
                    {"toolUse": {"toolUseId": "tu_1", "name": "query_gnomad", "input": {"pos": 42}}},
                ]
            }
        },
        "stopReason": "tool_use",
        "usage": {"inputTokens": 20, "outputTokens": 8},
    }
    fake_client = MagicMock()
    fake_client.converse.return_value = fake_response

    backend = BedrockBackend(model_id="anthropic.claude-3-5-haiku-20241022-v1:0")
    backend._client = fake_client  # bypass boto3.client() construction

    response = backend.generate(
        [
            Message(role="system", content="You are an agent."),
            Message(role="user", content="Interpret chr20:1 A>T"),
        ],
        tools=[{"function": {"name": "query_gnomad", "description": "…", "parameters": {}}}],
    )

    assert response.content == "Looking this up."
    assert response.has_tool_calls
    assert response.tool_calls[0] == ToolCall(name="query_gnomad", arguments={"pos": 42}, id="tu_1")
    assert response.usage == {"input_tokens": 20, "output_tokens": 8}

    call_kwargs = fake_client.converse.call_args.kwargs
    assert call_kwargs["modelId"] == "anthropic.claude-3-5-haiku-20241022-v1:0"
    assert call_kwargs["system"] == [{"text": "You are an agent."}]
    assert call_kwargs["toolConfig"]["tools"][0]["toolSpec"]["name"] == "query_gnomad"


def test_bedrock_generate_wraps_boto_errors_as_connection_error():
    from botocore.exceptions import ClientError

    fake_client = MagicMock()
    fake_client.converse.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "nope"}}, "Converse"
    )

    backend = BedrockBackend()
    backend._client = fake_client

    try:
        backend.generate([Message(role="user", content="hi")])
        assert False, "expected ConnectionError"
    except ConnectionError as e:
        assert "Bedrock" in str(e)


# ═══ Factory ══════════════════════════════════════════════════════════════════


def test_create_backend_resolves_azure_and_bedrock():
    assert isinstance(create_backend("azure_foundry"), AzureFoundryBackend)
    assert isinstance(create_backend("azure"), AzureFoundryBackend)
    assert isinstance(create_backend("bedrock"), BedrockBackend)
