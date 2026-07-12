from dataclasses import dataclass


@dataclass(frozen=True)
class OptimizerResult:
    step: str
    success: bool
    skipped: bool = False
    message: str = ""
    error: str | None = None
