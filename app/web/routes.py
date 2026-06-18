"""FastAPI route handlers.

Routes
------
GET  /                → Quota dashboard
GET  /namespaces      → Namespace selector + object count table
POST /namespaces      → Fetch object counts for the selected namespace
GET  /settings        → Settings form
POST /settings        → Save settings in-memory and redirect to /
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.clients.f5_xc_client import AuthError, F5XCClient, F5XCClientError
from app.config import get_settings, update_settings
from app.models.namespace import OBJECT_TYPE_TO_KIND, NamespaceObjectCounts
from app.models.quota import QuotaItem
from app.models.top_consumers import TopConsumersResult
from app.services.namespace_objects import fetch_namespaces, fetch_object_counts
from app.services.quota import fetch_quota_usages
from app.services.top_consumers import fetch_top_consumers

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> F5XCClient:
    """Return a client bound to the current in-memory settings."""
    return F5XCClient(get_settings())


def _not_configured_ctx(request: Request) -> dict:
    return {
        "error": (
            "F5 XC tenant and API key are not configured. "
            "Please visit <a href='/settings'>Settings</a> to configure them."
        ),
    }


# ---------------------------------------------------------------------------
# Quota dashboard
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def quota_dashboard(request: Request) -> HTMLResponse:
    """Render the quota dashboard page."""
    settings = get_settings()
    if not settings.is_configured:
        ctx = _not_configured_ctx(request)
        ctx["quota_items"] = []
        return templates.TemplateResponse(request, "quota.html", ctx)

    client = _make_client()
    quota_items: list[QuotaItem] = []
    error: str | None = None

    try:
        quota_items = await fetch_quota_usages(client)
    except AuthError:
        error = "Authentication failed. Please check your API token in Settings."
    except F5XCClientError as exc:
        logger.exception("Error fetching quota data")
        error = f"Could not load quota data: {exc}"

    return templates.TemplateResponse(
        request,
        "quota.html",
        {"quota_items": quota_items, "error": error},
    )


# ---------------------------------------------------------------------------
# Namespace object counts
# ---------------------------------------------------------------------------


@router.get("/namespaces", response_class=HTMLResponse)
async def namespaces_page(request: Request) -> HTMLResponse:
    """Render the namespace selector page (no namespace selected yet)."""
    settings = get_settings()
    if not settings.is_configured:
        ctx = _not_configured_ctx(request)
        ctx.update({"namespaces": [], "selected_ns": None, "object_counts": None})
        return templates.TemplateResponse(request, "namespace.html", ctx)

    client = _make_client()
    namespaces: list[str] = []
    error: str | None = None

    try:
        namespaces = await fetch_namespaces(client)
    except AuthError:
        error = "Authentication failed. Please check your API token in Settings."
    except F5XCClientError as exc:
        logger.exception("Error fetching namespaces")
        error = f"Could not load namespaces: {exc}"

    return templates.TemplateResponse(
        request,
        "namespace.html",
        {
            "namespaces": namespaces,
            "selected_ns": None,
            "object_counts": None,
            "error": error,
        },
    )


@router.post("/namespaces", response_class=HTMLResponse)
async def namespaces_counts(
    request: Request,
    namespace: str = Form(...),
) -> HTMLResponse:
    """Fetch and display object counts for the selected namespace."""
    settings = get_settings()
    if not settings.is_configured:
        ctx = _not_configured_ctx(request)
        ctx.update({"namespaces": [], "selected_ns": namespace, "object_counts": None})
        return templates.TemplateResponse(request, "namespace.html", ctx)

    client = _make_client()
    namespaces: list[str] = []
    object_counts: NamespaceObjectCounts | None = None
    error: str | None = None

    try:
        namespaces = await fetch_namespaces(client)
        object_counts = await fetch_object_counts(client, namespace)
    except AuthError:
        error = "Authentication failed. Please check your API token in Settings."
    except F5XCClientError as exc:
        logger.exception("Error fetching namespace object counts")
        error = f"Could not load data for namespace '{namespace}': {exc}"

    return templates.TemplateResponse(
        request,
        "namespace.html",
        {
            "namespaces": namespaces,
            "selected_ns": namespace,
            "object_counts": object_counts,
            "error": error,
        },
    )


# ---------------------------------------------------------------------------
# Top consumers
# ---------------------------------------------------------------------------


@router.get("/top-consumers", response_class=HTMLResponse)
async def top_consumers_page(request: Request) -> HTMLResponse:
    """Render the top consumers page (no object type selected yet)."""
    return templates.TemplateResponse(
        request,
        "top_consumers.html",
        {
            "object_types": OBJECT_TYPE_TO_KIND,
            "selected_kind": None,
            "selected_label": None,
            "result": None,
            "csd_result": None,
            "error": None,
        },
    )


@router.post("/top-consumers", response_class=HTMLResponse)
async def top_consumers_fetch(
    request: Request,
    kind: str = Form(...),
) -> HTMLResponse:
    """Fetch top namespaces for the selected object kind."""
    settings = get_settings()
    label = next((lbl for lbl, k in OBJECT_TYPE_TO_KIND.items() if k == kind), kind)

    if not settings.is_configured:
        ctx = _not_configured_ctx(request)
        ctx.update({
            "object_types": OBJECT_TYPE_TO_KIND,
            "selected_kind": kind,
            "selected_label": label,
            "result": None,
        })
        return templates.TemplateResponse(request, "top_consumers.html", ctx)

    client = _make_client()
    result: TopConsumersResult | None = None
    error: str | None = None

    try:
        result = await fetch_top_consumers(client, kind, label)
    except AuthError:
        error = "Authentication failed. Please check your API token in Settings."
    except F5XCClientError as exc:
        logger.exception("Error fetching top consumers")
        error = f"Could not load top consumers for '{label}': {exc}"

    return templates.TemplateResponse(
        request,
        "top_consumers.html",
        {
            "object_types": OBJECT_TYPE_TO_KIND,
            "selected_kind": kind,
            "selected_label": label,
            "result": result,
            "error": error,
        },
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Render the settings form pre-filled with current values."""
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "tenant": settings.tenant,
            # Never pre-fill the token in the HTML - force re-entry for security
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/settings")
async def settings_save(
    tenant: str = Form(...),
    api_token: str = Form(...),
) -> RedirectResponse:
    """Persist settings in-memory and redirect back to settings page."""
    update_settings(tenant=tenant, api_token=api_token)
    logger.info("Settings updated for tenant '%s'", tenant)
    return RedirectResponse(url="/settings?saved=1", status_code=303)
