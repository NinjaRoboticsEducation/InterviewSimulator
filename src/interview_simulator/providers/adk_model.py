from __future__ import annotations

from collections.abc import AsyncGenerator

from google import genai
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from pydantic import PrivateAttr

from .base import Binding, ProviderError
from .service import ProviderService


class CloudTextLlm(BaseLlm):
    """Text-only ADK adapter; credentials and transport stay private and excluded."""

    _service: ProviderService = PrivateAttr()
    _binding: Binding = PrivateAttr()
    _instruction: str = PrivateAttr()
    _schema: dict = PrivateAttr()
    _metadata: dict = PrivateAttr(default_factory=dict)
    _failure: ProviderError | None = PrivateAttr(default=None)

    @property
    def failure(self) -> ProviderError | None:
        return self._failure

    @property
    def metadata(self) -> dict:
        return dict(self._metadata)

    def __init__(self, service: ProviderService, binding: Binding, instruction: str, schema: dict):
        super().__init__(model=binding.model)
        self._service, self._binding = service, binding
        self._instruction, self._schema = instruction, schema

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        if llm_request.tools_dict:
            raise ValueError("Interview text tasks do not expose model-selected tools")
        prompt = "\n".join(p.text for content in llm_request.contents for p in content.parts or [] if p.text)
        try:
            text = await self._service.generate(self._binding, self._instruction, prompt, self._schema)
        except ProviderError as exc:
            self._failure = exc
            raise
        self._metadata = dict(self._service.last_call)
        yield LlmResponse(content=genai.types.Content(role="model", parts=[genai.types.Part(text=text)]))
