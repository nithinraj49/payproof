from fastapi import Depends, FastAPI
from fastapi.exceptions import HTTPException

from backend.auth import require_user_id
from backend.errors import ApiError, api_error_handler, http_exception_handler

app = FastAPI(title="PayProof API")
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/whoami")
def whoami(user_id: str = Depends(require_user_id)):
    return {"user_id": user_id}
