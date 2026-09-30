from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from google import genai
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from test_interview_flow import make_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from interview_practice import agent


def test_real_adk_chat_routes_job_choice_and_ten_answers(monkeypatch, tmp_path):
    practice = make_engine(tmp_path)
    monkeypatch.setattr(agent, "_engine", practice)
    monkeypatch.setattr(practice.wiki, "list_opportunities", list, raising=False)

    async def exercise():
        service = InMemorySessionService()
        await service.create_session(app_name="interview_practice", user_id="local", session_id="chat")
        runner = Runner(agent=agent.root_agent, app_name="interview_practice", session_service=service)

        async def say(message):
            events = [
                event
                async for event in runner.run_async(
                    user_id="local",
                    session_id="chat",
                    new_message=genai.types.Content(role="user", parts=[genai.types.Part(text=message)]),
                )
            ]
            return "\n".join(
                part.text or "" for event in events if event.content for part in event.content.parts
            )

        assert "Ready opportunities" in await say("jobs")
        assert "1/10" in await say("start example/engineer en")
        for number in range(1, 11):
            response = await say(f"Answer {number}")
            assert f"{number + 1}/10" in response if number < 10 else "interview is complete" in response
        saved_session = await service.get_session(
            app_name="interview_practice", user_id="local", session_id="chat"
        )
        assert len(practice.store.get_run(saved_session.state["interview_run_id"])["answers"]) == 10
        assert "Report generation started" in await say("report")

    asyncio.run(exercise())
