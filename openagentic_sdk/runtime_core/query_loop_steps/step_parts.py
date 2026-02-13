from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ...providers.base import ModelOutput

from .types import StepState


@dataclass(frozen=True, slots=True)
class StepPreDone:
    state: StepState
    model_out: ModelOutput
    model_ctx: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class StepPostDone:
    state: StepState
    should_continue: bool

