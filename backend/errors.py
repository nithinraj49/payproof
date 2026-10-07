"""The single JSON error shape used by every /api route (REQUIREMENTS.md section 10)."""
from typing import Any, Optional

from fastapi import HTTPException
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    def __init__(self, status_code: int, error_code: str, message: str, detail: Optional[Any] = None):
        super().__init__(status_code=status_code, detail=message)
        self.error_code = error_code
        self.message = message
        self.error_detail = detail


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    body = {"error_code": exc.error_code, "message": exc.message}
    if exc.error_detail is not None:
        body["detail"] = exc.error_detail
    return JSONResponse(status_code=exc.status_code, content=body)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "http_error", "message": str(exc.detail)},
    )
