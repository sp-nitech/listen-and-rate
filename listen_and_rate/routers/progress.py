"""GET /progress - per-rater assignment coverage (FastAPI only)."""

from __future__ import annotations

import html as _html
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ..config import Config
from ..dependencies import get_config
from ..progress import collect_progress

router = APIRouter()

_STATUS_LABEL = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "complete": "Complete",
}


@router.get("/progress", response_class=HTMLResponse, include_in_schema=False)
def get_progress_page(config: Config = Depends(get_config)) -> HTMLResponse:
    """Render a table of each rater's assigned vs saved items."""
    data = collect_progress(config)
    return HTMLResponse(content=_page_html(data))


def _page_html(data: dict) -> str:
    title = _html.escape(data.get("title") or "Rater progress")
    experiment_id = _html.escape(data.get("experiment_id") or "")
    raters: list[dict] = data.get("raters") or []
    assigned = [r for r in raters if r.get("in_assignments")]
    extras = [r for r in raters if not r.get("in_assignments")]
    body = [_summary_table(assigned, extras)]
    if assigned:
        body.append("<h2>Assigned raters</h2>")
        body.extend(_rater_details(r) for r in assigned)
    if extras:
        body.append("<h2>Unassigned sessions</h2>")
        body.extend(_rater_details(r) for r in extras)
    if not raters:
        body.append(
            "<p class='progress-empty'>No assignments and no saved ratings yet.</p>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Progress — {title}</title>
  <link rel="icon" href="data:,">
  <script>
    if (localStorage.getItem('theme') === 'light') {{
      document.documentElement.setAttribute('data-theme', 'light');
    }}
  </script>
  <link rel="stylesheet" href="/css/style.css">
</head>
<body class="progress-page">
  <main class="progress-main">
    <h1>Rater progress</h1>
    <p class="progress-meta">
      {_html.escape(data.get("title") or "")}
      · <code>{experiment_id}</code>
    </p>
    {"".join(body)}
  </main>
</body>
</html>
"""


def _summary_table(assigned: list[dict], extras: list[dict]) -> str:
    rows = [_summary_row(r) for r in assigned] + [_summary_row(r) for r in extras]
    if not rows:
        return ""
    return f"""
    <table class="progress-table">
      <thead>
        <tr>
          <th>Rater</th>
          <th>Completed</th>
          <th>Status</th>
          <th>Last update</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows)}
      </tbody>
    </table>
    """


def _summary_row(row: dict) -> str:
    rater = row.get("rater") or "(unknown)"
    href = f"/?rater={quote(rater, safe='')}"
    status = _status_text(row)
    last = _html.escape(row["last_updated"]) if row.get("last_updated") else "—"
    count = f"{row.get('completed_count', 0)} / {row.get('assigned_count', 0)}"
    if not row.get("in_assignments"):
        count = f"{row.get('completed_count', 0)} (unassigned)"
    status_class = _html.escape(row.get("status") or "")
    status_html = (
        f'<span class="progress-status progress-status-{status_class}">'
        f"{_html.escape(status)}</span>"
    )
    return f"""
        <tr>
          <td><code>{_html.escape(rater)}</code></td>
          <td>{_html.escape(count)}</td>
          <td>{status_html}</td>
          <td>{last}</td>
          <td><a href="{href}">Open test</a></td>
        </tr>
    """


def _rater_details(row: dict) -> str:
    rater = row.get("rater") or "(unknown)"
    items = row.get("items") or []
    rows = []
    for item in items:
        answers = item.get("answers")
        if item.get("status") == "done" and isinstance(answers, dict):
            scores = (
                ", ".join(
                    f"{_html.escape(str(k))}={_html.escape(str(v))}"
                    for k, v in answers.items()
                )
                or "saved"
            )
        else:
            scores = "pending"
        rows.append(
            f"<tr><td><code>{_html.escape(str(item.get('item')))}</code></td>"
            f"<td>{scores}</td></tr>"
        )
    inner = "".join(rows) if rows else "<tr><td colspan=2>No items</td></tr>"
    return f"""
    <details class="progress-rater">
      <summary>
        <code>{_html.escape(rater)}</code>
        — {_html.escape(_status_text(row))}
        ({row.get("completed_count", 0)}/{row.get("assigned_count", 0)})
      </summary>
      <table class="progress-items">
        <thead><tr><th>Item</th><th>Ratings</th></tr></thead>
        <tbody>{inner}</tbody>
      </table>
    </details>
    """


def _status_text(row: dict) -> str:
    label = _STATUS_LABEL.get(row.get("status") or "", row.get("status") or "")
    if row.get("awaiting_finish"):
        return f"{label} (awaiting finish)"
    return label
