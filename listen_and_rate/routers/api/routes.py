"""API routes: /api/status, /api/config, /api/submit.

Each endpoint dispatches to the per-test-type handler module in the project's
canonical order: MOS, DMOS, CMOS, AB, ABX, XAB, MUSHRA.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...config import (
    ABConfig,
    ABXConfig,
    CMOSConfig,
    Config,
    DMOSConfig,
    MOSConfig,
    XABConfig,
)
from ...dependencies import get_config, get_result_saver, get_x_secret
from ...models import SubmitRequest
from ...storage import ResultExistsError, ResultSaver
from .ab import _get_ab_test_config, _submit_ab
from .abx import _get_abx_test_config, _submit_abx
from .cmos import _get_cmos_test_config, _submit_cmos
from .dmos import _get_dmos_test_config, _submit_dmos
from .mos import _get_mos_test_config, _submit_mos
from .mushra import _get_mushra_test_config, _submit_mushra
from .xab import _get_xab_test_config, _submit_xab

router = APIRouter()


@router.get("/status")
def status(config: Config = Depends(get_config)):
    """Health-check endpoint; also confirms the loaded test type."""
    return {"status": "ok", "test_type": config.test_type}


@router.get("/config")
def get_test_config(
    config: Config = Depends(get_config), x_secret: bytes = Depends(get_x_secret)
):
    """Return test parameters for the frontend.

    Only id and label are sent per stimulus - path, system, and utterance are
    withheld to keep listeners blind to the underlying system under test.
    """
    if isinstance(config, MOSConfig):
        return _get_mos_test_config(config)
    if isinstance(config, DMOSConfig):
        return _get_dmos_test_config(config)
    if isinstance(config, CMOSConfig):
        return _get_cmos_test_config(config)
    if isinstance(config, ABConfig):
        return _get_ab_test_config(config)
    if isinstance(config, ABXConfig):
        return _get_abx_test_config(config, x_secret)
    if isinstance(config, XABConfig):
        return _get_xab_test_config(config)
    return _get_mushra_test_config(config)


@router.post("/submit")
def submit(
    body: SubmitRequest,
    config: Config = Depends(get_config),
    saver: ResultSaver = Depends(get_result_saver),
    x_secret: bytes = Depends(get_x_secret),
):
    """Validate and persist a complete set of listener responses.

    Returns 409 when results for the session_id already exist - collected
    data is never overwritten (see storage.ResultExistsError).
    """
    try:
        if isinstance(config, MOSConfig):
            return _submit_mos(body, config, saver)
        if isinstance(config, DMOSConfig):
            return _submit_dmos(body, config, saver)
        if isinstance(config, CMOSConfig):
            return _submit_cmos(body, config, saver)
        if isinstance(config, ABConfig):
            return _submit_ab(body, config, saver)
        if isinstance(config, ABXConfig):
            return _submit_abx(body, config, saver, x_secret)
        if isinstance(config, XABConfig):
            return _submit_xab(body, config, saver)
        return _submit_mushra(body, config, saver)
    except ResultExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
