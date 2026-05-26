"""FastAPI application factory.

Start the development server with:
    uvicorn app.main:app --reload

Or in production:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.web.routes import router

# Configure basic logging so structured log messages appear in the console.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="F5 XC Dashboard",
    description="Quota and namespace object viewer for F5 Distributed Cloud.",
    version="0.1.0",
)

app.include_router(router)
