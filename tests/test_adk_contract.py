from __future__ import annotations

import asyncio
import os

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

from google import genai
from google.adk import Agent, Runner, Workflow
from google.adk.models.lite_llm import LiteLlm, LiteLLMClient
from google.adk.sessions import DatabaseSessionService
from litellm import ModelResponse


def test_pinned_adk_graph_and_sqlite_session(tmp_path):
    async def exercise():
        def echo(node_input: str) -> str:
            return "Graph received: " + node_input

        service = DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{tmp_path / 'adk.sqlite'}")
        workflow = Workflow(name="contract_graph", edges=[("START", echo)])
        runner = Runner(node=workflow, app_name="contract", session_service=service)
        await service.create_session(app_name="contract", user_id="local", session_id="one")
        message = genai.types.Content(role="user", parts=[genai.types.Part(text="hello")])
        events = [
            event async for event in runner.run_async(user_id="local", session_id="one", new_message=message)
        ]
        assert events
        assert (tmp_path / "adk.sqlite").is_file()

    asyncio.run(exercise())


def test_litellm_endpoint_is_explicit_loopback():
    model = LiteLlm(model="openai/interview-local", api_base="http://127.0.0.1:8081/v1", api_key="local-only")
    assert model._additional_args["api_base"] == "http://127.0.0.1:8081/v1"


def test_adk_agent_node_uses_local_litellm_adapter(tmp_path):
    class StubClient(LiteLLMClient):
        async def acompletion(self, model, messages, tools, **kwargs):
            assert model == "openai/interview-local"
            assert kwargs["api_base"] == "http://127.0.0.1:8081/v1"
            return ModelResponse(
                id="stub",
                model=model,
                choices=[
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"ok": true}'},
                        "finish_reason": "stop",
                    }
                ],
            )

    async def exercise():
        service = DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{tmp_path / 'model.sqlite'}")
        model = LiteLlm(
            model="openai/interview-local",
            api_base="http://127.0.0.1:8081/v1",
            api_key="local-only",
            llm_client=StubClient(),
        )
        agent = Agent(name="local_agent", model=model, instruction="Return JSON")
        workflow = Workflow(name="local_graph", edges=[("START", agent)])
        runner = Runner(node=workflow, app_name="contract", session_service=service)
        await service.create_session(app_name="contract", user_id="local", session_id="model")
        message = genai.types.Content(role="user", parts=[genai.types.Part(text="test")])
        events = [
            event
            async for event in runner.run_async(user_id="local", session_id="model", new_message=message)
        ]
        assert any(event.is_final_response() for event in events)

    asyncio.run(exercise())
