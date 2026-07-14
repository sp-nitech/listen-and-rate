"""GET /report - real-time MOS results page (FastAPI only)."""

from __future__ import annotations

import html as _html
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ..config import Config
from ..dependencies import get_config

router = APIRouter()


@router.get("/report", response_class=HTMLResponse, include_in_schema=False)
def get_report(config: Config = Depends(get_config)) -> HTMLResponse:
    """Return a standalone Plotly HTML report for the current experiment's results."""
    from ..analysis import generate_report_html

    results_dir = Path(config.output.path) / config.experiment_id
    paths = (
        sorted([*results_dir.glob("*.csv"), *results_dir.glob("*.json")])
        if results_dir.is_dir()
        else []
    )

    if not paths:
        return HTMLResponse(content=_no_data_html(str(results_dir)))

    try:
        html = generate_report_html(paths, title=config.title)
        return HTMLResponse(content=html)
    except ImportError as exc:
        return HTMLResponse(content=_error_html(str(exc)), status_code=503)
    except Exception as exc:
        return HTMLResponse(content=_error_html(str(exc)), status_code=500)


def _no_data_html(path: str) -> str:
    return (
        "<!doctype html><html><head><meta charset=utf-8></head><body>"
        "<h2>No results yet</h2>"
        f"<p>No result files found in: <code>{_html.escape(path)}</code></p>"
        "<p>Complete some evaluations and submit ratings first.</p>"
        "</body></html>"
    )


def _error_html(msg: str) -> str:
    return (
        "<!doctype html><html><head><meta charset=utf-8></head><body>"
        "<h2>Error generating report</h2>"
        f"<pre>{_html.escape(msg)}</pre>"
        "</body></html>"
    )
