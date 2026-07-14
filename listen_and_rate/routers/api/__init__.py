"""API router package: /api/status, /api/config, /api/submit.

The router and its endpoint functions live in routes.py; per-test-type request
handling is split across mos/dmos/cmos/ab/abx/xab/mushra, sharing _shared.
"""

from __future__ import annotations

from .routes import get_test_config, router, submit

__all__ = ["get_test_config", "router", "submit"]
