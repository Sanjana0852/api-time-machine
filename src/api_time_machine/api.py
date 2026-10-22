"""The web API: comparison and replay over HTTP (section 7 of docs/api-replay-design.md).

Run it with:  python -m uvicorn api_time_machine.api:app --port 8000
Interactive docs: http://localhost:8000/docs
"""

import math
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, Field, JsonValue

from api_time_machine import __version__
from api_time_machine.config import allowed_hosts_from_env, load_env_file
from api_time_machine.diff import compare
from api_time_machine.fetch import BlockedURLError, FetchError
from api_time_machine.models import Change, ChangeKind, Severity
from api_time_machine.replay import replay


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runs once when the server starts. Loading .env here (not at import time)
    # means tests that import this module aren't affected by a local .env file.
    load_env_file()
    yield


app = FastAPI(
    title="API Time Machine",
    description="Detect breaking changes between two API responses.",
    version=__version__,
    lifespan=lifespan,
)


# --- Request validation ----------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    """Return 422 with each problem's location and message, but not the input.

    FastAPI's default handler echoes the invalid input back, which crashes when
    the input contains NaN (it can't be written as JSON), and would repeat
    whole documents in every error. "ctx" can hold Python exception objects.
    """
    details = [
        {key: value for key, value in problem.items() if key not in ("input", "ctx")}
        for problem in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})



def _reject_non_finite_numbers(value: JsonValue) -> JsonValue:
    # FastAPI accepts NaN and Infinity in request bodies, but they aren't valid
    # JSON and NaN != NaN would create fake changes. Files and fetched responses
    # reject them too (jsonparse.py), so every entry point follows the same rule.
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NaN and Infinity are not allowed in JSON")
    if isinstance(value, dict):
        for item in value.values():
            _reject_non_finite_numbers(item)
    elif isinstance(value, list):
        for item in value:
            _reject_non_finite_numbers(item)
    return value


# Pydantic's JsonValue keeps types exactly as sent (true stays a bool, 250.0
# stays a float), which the engine relies on to detect type changes.
StrictJsonValue = Annotated[JsonValue, AfterValidator(_reject_non_finite_numbers)]


class CompareRequest(BaseModel):
    old: StrictJsonValue = Field(description="The old JSON document")
    new: StrictJsonValue = Field(description="The new JSON document")


class ReplayRequest(BaseModel):
    # Plain strings: fetch.py is the single place that decides which URLs are
    # allowed, so the rules can't drift apart.
    old_url: str = Field(
        min_length=1, max_length=2048, examples=["http://localhost:8001/v1/products/101"]
    )
    new_url: str = Field(
        min_length=1, max_length=2048, examples=["http://localhost:8001/v2/products/101"]
    )


# --- Response shapes -----------------------------------------------------------------------


class ChangeOut(BaseModel):
    path: str
    kind: ChangeKind
    severity: Severity
    old_value: JsonValue
    new_value: JsonValue


class Summary(BaseModel):
    total: int
    breaking: int
    safe: int
    info: int
    has_breaking: bool


class CompareResponse(BaseModel):
    changes: list[ChangeOut]
    summary: Summary


class ResponseInfo(BaseModel):
    url: str
    status_code: int


class ReplayResponse(CompareResponse):
    old: ResponseInfo
    new: ResponseInfo
    status_severity: Severity | None = Field(
        description="Severity of the status code change, or null if both codes are equal"
    )


# --- Dependencies (overridden in tests) ---------------------------------------------------


async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """Provide an HTTP client for one request, closing it afterwards."""
    async with httpx.AsyncClient() as client:
        yield client


def get_allowed_hosts() -> frozenset[str]:
    return allowed_hosts_from_env()


# --- Endpoints -------------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the server is running."""
    return {"status": "ok"}


@app.post("/compare")
def compare_documents(request: CompareRequest) -> CompareResponse:
    """Compare two JSON documents sent in the request body."""
    changes = compare(request.old, request.new)
    return CompareResponse(changes=_change_models(changes), summary=_summarize(changes))


@app.post(
    "/replay",
    responses={
        400: {"description": "A URL was refused by a safety rule (e.g. host not allowed)"},
        502: {"description": "A target server failed, timed out, or didn't return JSON"},
    },
)
async def replay_urls(
    request: ReplayRequest,
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    allowed_hosts: Annotated[frozenset[str], Depends(get_allowed_hosts)],
) -> ReplayResponse:
    """Fetch both URLs and compare the responses, including status codes."""
    try:
        result = await replay(client, request.old_url, request.new_url, allowed_hosts)
    # BlockedURLError first: it's a subclass of FetchError.
    except BlockedURLError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    except FetchError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None

    return ReplayResponse(
        old=ResponseInfo(url=result.old.url, status_code=result.old.status_code),
        new=ResponseInfo(url=result.new.url, status_code=result.new.status_code),
        status_severity=result.status_severity,
        changes=_change_models(result.changes),
        summary=_summarize(result.changes, result.status_severity),
    )


# --- Helpers ---------------------------------------------------------------------------------


def _change_models(changes: list[Change]) -> list[ChangeOut]:
    return [ChangeOut.model_validate(change, from_attributes=True) for change in changes]


def _summarize(changes: list[Change], status_severity: Severity | None = None) -> Summary:
    counts = Counter(change.severity for change in changes)
    return Summary(
        total=len(changes),
        breaking=counts[Severity.BREAKING],
        safe=counts[Severity.SAFE],
        info=counts[Severity.INFO],
        has_breaking=counts[Severity.BREAKING] > 0 or status_severity is Severity.BREAKING,
    )
