from typing import Protocol, runtime_checkable

DECISION_THRESHOLD: float
PROMPT_VERSION: str

@runtime_checkable
class DecisionBackend(Protocol):
    model_id: str
    def decide(self, justification: str, rule: str | None, context: str | None) -> float: ...

class FakeBackend:
    model_id: str
    def __init__(self, score: float = 1.0) -> None: ...
    def decide(self, justification: str, rule: str | None, context: str | None) -> float: ...

def get_backend() -> DecisionBackend | None: ...
