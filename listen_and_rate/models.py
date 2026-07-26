"""Pydantic models for API request bodies."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .ids import is_valid_id

# Seconds the listener took on the page this answer came from, measured by the
# frontend (see listening-test.js). allow_inf_nan keeps a broken client from
# writing "inf"/"nan" into a results file. Stored only when the config opts in;
# absent otherwise, and never required.
_RESPONSE_TIME = Field(default=None, allow_inf_nan=False)


class RatingEntry(BaseModel):
    """A single rating submitted by a listener.

    On its own for MOS, or relative to a reference stimulus for DMOS.
    """

    stimulus_id: str
    reference_id: str | None = None  # DMOS only: what this rating is relative to
    rating: int
    response_time: float | None = _RESPONSE_TIME


class ChoiceEntry(BaseModel):
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
    response_time: float | None = _RESPONSE_TIME


class SubmitRequest(BaseModel):
    """Payload sent to POST /api/submit at the end of a test session."""

    # Names the result file inside the experiment's directory, so it is held
    # to the same rule as experiment_id and rejected (422) rather than
    # rewritten when it does not fit - see listen_and_rate/ids.py, mirrored
    # by frontend/save.php. The browser sends a UUID, which always fits.
    session_id: str
    test_type: str
    ratings: list[RatingEntry] = Field(default_factory=list)  # MOS, DMOS, MUSHRA
    choices: list[ChoiceEntry] = Field(default_factory=list)  # CMOS, AB, ABX, XAB
    metadata: dict[str, str] = Field(default_factory=dict)  # pre-test form answers
    survey: dict[str, str] = Field(default_factory=dict)  # post-test form answers

    @field_validator("session_id")
    @classmethod
    def session_id_must_be_path_safe(cls, v: str) -> str:
        """Reject a session_id that could not name a file in the results dir."""
        if not is_valid_id(v):
            raise ValueError(
                "session_id must contain only letters, digits, '.', '-', or "
                "'_' (and cannot be '.' or '..')"
            )
        return v
