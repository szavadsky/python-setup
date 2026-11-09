from typing import Protocol, runtime_checkable

DECISION_THRESHOLD: float = 0.5
PROMPT_VERSION: str = "prompt-v1"


@runtime_checkable
class DecisionBackend(Protocol):
    model_id: str

    def decide(self, justification: str, rule: str | None, context: str | None) -> float: ...


class FakeBackend:
    model_id: str = "fake-backend rev test prompt-v1"

    def __init__(self, score: float = 1.0) -> None:
        raise NotImplementedError("FakeBackend stub")

    def decide(self, justification: str, rule: str | None, context: str | None) -> float:
        raise NotImplementedError("FakeBackend.decide stub")


def get_backend() -> DecisionBackend | None:
    raise NotImplementedError("get_backend stub")


def _reset_backend_state() -> None:
    pass
