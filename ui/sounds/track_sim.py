"""Track→Track helpers (Trainz: play A one-shot → stop → loop B)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TrackPair:
    a_idx: int
    b_idx: int

    def valid(self, n_clips: int) -> bool:
        return (
            0 <= self.a_idx < n_clips
            and 0 <= self.b_idx < n_clips
            and self.a_idx != self.b_idx
        )


# State labels for UI / tests
PHASE_IDLE = "idle"
PHASE_A = "playing_a"
PHASE_SEAM = "seam"
PHASE_B = "looping_b"


def next_phase_after_a_done(current: str) -> str:
    """idle/playing_a → seam → looping_b."""
    if current == PHASE_A:
        return PHASE_SEAM
    return current
