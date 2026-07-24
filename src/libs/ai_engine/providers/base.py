from __future__ import annotations

from typing import Protocol

from ..models import LLMRequest


class ChatClient(Protocol):
    def invoke(self, messages: list[dict[str, str]]): ...


class ClientFactory(Protocol):
    def __call__(self, request: LLMRequest) -> ChatClient: ...

