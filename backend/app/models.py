"""Pydantic request/response schemas for the search API.

These models define the JSON shapes that FastAPI validates on the way in
(requests) and serialises on the way out (responses).
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class SearchResult(BaseModel):
    """A single matching keyframe returned by a search.

    Attributes:
        frame: Image filename of the keyframe.
        distance: Match score for this frame (higher = better match).
        url: Absolute URL where the keyframe image is served.
        name: Same as ``frame``; kept for convenience on the frontend.
    """
    frame: str
    distance: float
    url: str
    name: str

    class Config:
        json_schema_extra = {
            "example": {
                "frame": "L04_V001-Scene-119-01-407600.jpg",
                "distance": 0.15,
                "url": 'http://example.com/1'
            }
        }


class SearchResponse(BaseModel):
    """Envelope returned by every search endpoint.

    Attributes:
        total_results: Number of matches found before limiting.
        returned_results: Number of matches actually included in ``results``.
        results: The matching keyframes.
        query_type: Kind of search performed, e.g. ``"text"`` or ``"filter"``.
        processing_time: Server-side search time in seconds.
        max_distance: Highest score among the results (used by the UI to scale bars).
    """
    total_results: int
    returned_results: int
    results: List[SearchResult]
    query_type: str
    processing_time: float
    max_distance: float = Field(..., description="Maximum distance value among all results")

    class Config:
        json_schema_extra = {
            "example": {
                "total_results": 150,
                "returned_results": 10,
                "results": [
                    {
                "frame": "L04_V001-Scene-119-01-407600.jpg",
                "distance": 0.15,
                 "url": 'http://example.com/1'
                    }
                ],
                "query_type": "text",
                "processing_time": 0.234,
                "max_distance": 0.85
            }
        }


class TextSearchRequest(BaseModel):
    """Request body for the text-based search endpoints.

    Attributes:
        query: The natural-language query (must be non-empty).
        limit: Maximum number of frames to return.
        rank: How many top frames to keep per video before aggregating.
        unique_keyword: Optional distinctive keyword used as a priority tie-breaker.
    """
    query: str = Field(..., min_length=1, description="Text query for search")
    limit: int = Field(10, ge=1, le=10000, description="Maximum number of results to return")
    rank: int = Field(3, ge=1, le=50, description="Rank to given out related video")
    unique_keyword: str

    class Config:
        json_schema_extra = {
            "example": {
                "query": "person walking in the park",
                "limit": 20
            }
        }


class FilterRequest(BaseModel):
    """Request body for ``/filter-search``: filter keyframes by tag fields.

    All filters are optional; any provided value is matched against the matching
    tag field of each keyframe.
    """
    color: Optional[str] = Field(None, description="Filter by color")
    action: Optional[str] = Field(None, description="Filter by action")
    object: Optional[str] = Field(None, description="Filter by object")
    ocr: Optional[str] = Field(None, description="Filter by OCR text")
    limit: Optional[int] = Field(30, description="Number of results to return")

    class Config:
        json_schema_extra = {
            "example": {
                "color": "Red",
                "action": "Paris",
                "object": "Car",
                "limit": 30
            }
        }
