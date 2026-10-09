"""ERDDAP-shaped error responses (#36).

Real ERDDAP answers every error as plain text::

    Error {
        code=404;
        message="Not Found: Currently unknown datasetID=nonexistent";
    }

erddapy puts the whole body in the ``HTTPError`` it raises, and rerddap prints
it, so users see this text. A plugin cannot add app-wide exception handlers,
so, as xpublish-ogc-core does for OGC errors, the routers use a route class
that turns errors into this body. Ported from ERDDAP's ``EDStatic.lowSendError``
and ``String2.toJson`` (github.com/ERDDAP/erddap ``main``, 2026-10-07).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute

logger = logging.getLogger("uvicorn")

#: ERDDAP's error media type, charset included, as real servers send it.
ERROR_MEDIA_TYPE = "text/plain;charset=UTF-8"

#: The prefixes ERDDAP puts before a message, by status. Other statuses get
#: none, as in ERDDAP.
REASONS = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    408: "Request Timeout",
    413: "Payload Too Large",
    416: "Requested Range Not Satisfiable",
    422: "Unprocessable Content",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def quote(text: str) -> str:
    """ERDDAP's ``String2.toJson(s, 65536, false)``: a quoted string.

    Quotes and backslashes are escaped and newlines kept as they are; other
    control characters are escaped, and a backspace is dropped.
    """
    out = ['"']
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\n")
        elif ch == "\b":
            continue
        elif ch in "\f\r\t":
            out.append({"\f": "\\f", "\r": "\\r", "\t": "\\t"}[ch])
        elif ord(ch) < 32:  # noqa: PLR2004
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def error_body(status: int, message: str) -> str:
    """ERDDAP's error text for ``status`` and ``message``."""
    message = message.strip() or "(no details)"
    if status in REASONS:
        message = f"{REASONS[status]}: {message}"
    return f"Error {{\n    code={status};\n    message={quote(message)};\n}}\n"


def error_response(status: int, message: str, headers: dict | None = None) -> Response:
    """An ERDDAP error response."""
    return PlainTextResponse(
        error_body(status, message),
        status_code=status,
        headers=headers,
        media_type=ERROR_MEDIA_TYPE,
    )


class ErddapRoute(APIRoute):
    """A route that answers errors as ERDDAP does.

    ``HTTPException`` keeps its status. A request FastAPI cannot validate is a
    400, as ERDDAP reports a bad query. Anything unexpected is logged with its
    traceback and answered with a 500 in ERDDAP's form.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Wrap FastAPI's handler to catch errors."""
        handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except HTTPException as exc:
                return error_response(exc.status_code, str(exc.detail), exc.headers)
            except RequestValidationError as exc:
                problems = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                )
                return error_response(400, f"Query error: {problems}")
            except Exception as exc:
                logger.exception("ERDDAP: unexpected error for %s", request.url)
                return error_response(500, f"{type(exc).__name__}: {exc}")

        return route_handler
