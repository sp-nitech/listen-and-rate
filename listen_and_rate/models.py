"""Pydantic models for API request bodies."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RatingItem(BaseModel):
    """A single rating submitted by a listener.

    On its own for MOS, or relative to a reference stimulus for DMOS.
    """

    stimulus_id: str
    reference_id: str | None = None  # DMOS only: what this rating is relative to
    rating: int


class ChoiceItem(BaseModel):
    """A single AB/ABX/CMOS trial's outcome submitted by a listener.

    stimulus_ids is the pair of stimuli shown for this trial.
    selected_stimulus_id is which one the listener chose - None for AB's
    tie/no-preference response (ABX has no such option today, but nothing
    stops a future extension from allowing it).
    x_token is only used for ABX: the opaque token echoed back from
    /api/config, used server-side to recover the ground truth without
    session storage.
    rating is only used for CMOS: the signed comparison rating (-3..3) of
    stimulus_ids[1] relative to stimulus_ids[0], as shown to the listener.
    """

    stimulus_ids: list[str]
    selected_stimulus_id: str | None = None
    x_token: str | None = None
    rating: int | None = None


class SubmitRequest(BaseModel):
    """Payload sent to POST /api/submit at the end of a test session."""

    session_id: str
    test_type: str
    ratings: list[RatingItem] = Field(default_factory=list)  # MOS, DMOS, MUSHRA
    choices: list[ChoiceItem] = Field(default_factory=list)  # CMOS, AB, ABX, XAB
    metadata: dict[str, str] = Field(default_factory=dict)
