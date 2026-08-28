# backend\asr_api\main.py

from typing import Any
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from asr_api import runtime


logger = logging.getLogger(__name__)
app    = FastAPI(title = "AIC 2026 ASR Service")


class SearchRequest(BaseModel) :
    query           : str = Field(min_length = 1)
    limit           : int = Field(default = 50, gt = 0)
    windows_per_hit : int = Field(default = 3, gt = 0)


@app.get("/health")
def health() -> dict[str, bool] :
    return {"ok" : True}


@app.get("/status")
def status() -> dict[str, Any] :
    return runtime.asr_status()


@app.post("/search")
def search(request : SearchRequest) -> dict[str, Any] :
    try :
        return runtime.search_asr(
            request.query,
            top_k = request.limit,
            windows_per_hit = request.windows_per_hit,
        )
    except Exception as error :
        logger.exception("ASR search failed")
        raise HTTPException(status_code = 503, detail = "ASR retrieval unavailable") from error