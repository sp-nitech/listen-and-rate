"""GET /report - real-time MOS results page (FastAPI only)."""

from __future__ import annotations

import html as _html
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..dependencies import STAGE_PARAM, get_config, get_sequence

router = APIRouter()


@router.get("/report", response_class=HTMLResponse, include_in_schema=False)
def get_report(
    request: Request, sequence: list[str] | None = Depends(get_sequence)
) -> HTMLResponse:
    """Return a standalone Plotly HTML report for the current experiment's results.

    A sequence holds one report per test, so asked for none in particular it
    lists a link to each instead.
    """
    from ..analysis import generate_report_html

    if sequence is not None:
        return HTMLResponse(content=_stage_index_html(sequence))
    # Resolved here rather than through Depends: a sequence asked for no stage
    # is answered above, and get_config would have rejected it first.
    config = get_config(request)
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


def _stage_index_html(stage_ids: list[str]) -> str:
    items = "".join(
        f'<li><a href="report?{STAGE_PARAM}={quote(stage_id)}">'
        f"{_html.escape(stage_id)}</a></li>"
        for stage_id in stage_ids
    )
    return (
        "<!doctype html><html><head><meta charset=utf-8></head><body>"
        "<h2>Reports</h2>"
        "<p>This server runs several tests in sequence. Each has its own report:</p>"
        f"<ul>{items}</ul>"
        "</body></html>"
    )


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
