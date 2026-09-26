"""Cổng 503 trong lúc warm-up (main._blocked_during_warmup).

Lý do tồn tại: deploy 5.3.7 chết ở warm-up với KeyError: 'M02_V017' vì /status
gọi _load_meta() song song với warm-up — xem chú thích ở main.py.
"""

import pytest

from app.main import _blocked_during_warmup


@pytest.mark.parametrize("path", [
    "/status",
    "/ensemble-search",
    "/single-search",
    "/temporal-search",
    "/temporal-search-candidates",
    "/trake-search-text",
    "/ocr-search",
    "/ocr-text/L21_V001-0000-3.jpg",
])
def test_loader_routes_are_blocked_while_warming(path):
    assert _blocked_during_warmup("GET", path, "warming")
    assert _blocked_during_warmup("POST", path, "warming")


@pytest.mark.parametrize("path", ["/health", "/", "/api/auth/login", "/api/board",
                                  "/api/dres/current-task", "/api/dres/status"])
def test_light_routes_stay_open_while_warming(path):
    # /health phải trả lời trong lúc warm-up: smoke test và UI đọc warmup.state ở đó.
    assert not _blocked_during_warmup("GET", path, "warming")
    assert not _blocked_during_warmup("POST", path, "warming")


def test_dres_submit_and_benchmark_run_blocked_but_reads_are_not():
    # POST /api/dres/submissions quy ms -> frame qua preprocess._load_meta().
    assert _blocked_during_warmup("POST", "/api/dres/submissions", "warming")
    assert _blocked_during_warmup("POST", "/api/dres/submissions/7/approve", "warming")
    assert _blocked_during_warmup("POST", "/api/evaluation/runs", "warming")
    assert not _blocked_during_warmup("GET", "/api/dres/submissions", "warming")
    assert not _blocked_during_warmup("GET", "/api/evaluation/runs", "warming")


@pytest.mark.parametrize("state", ["cold", "ready", "failed"])
def test_nothing_blocked_outside_warming(state):
    # "cold" = AIC_WARMUP=0: không có warm-up nào chạy, mọi thứ nạp lười như cũ.
    # "failed": vẫn cho nạp lười để dùng tạm thay vì khoá chết cả API.
    for path in ("/status", "/ensemble-search", "/api/dres/submissions"):
        assert not _blocked_during_warmup("GET", path, state)
        assert not _blocked_during_warmup("POST", path, state)
