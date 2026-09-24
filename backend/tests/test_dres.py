# -*- coding: utf-8 -*-
"""Nộp bài DRES: đề xuất → duyệt → gửi, chạy với một DRES giả.

Mỗi lần nộp sai là −10 điểm, nên phần lớn test ở đây kiểm những đường KHÔNG
được gửi: bấm đúp, đề xuất trùng, câu đã đổi, video không rõ fps.
"""
import json

import pytest
from fastapi import HTTPException

from app import dres, preprocess
from app.db.connection import utcnow_iso
from app.routers import dres as router

FPS = 29.97


class FakeDres:
    """Đủ năm endpoint client của DRES v2, theo doc/oas-client.json."""

    def __init__(self):
        self.password = "pw"
        self.sessions: set[str] = set()
        self.logins = 0
        self.evaluations = [
            {"id": "ev-1", "name": "Chung ket", "type": "SYNCHRONOUS", "status": "ACTIVE"},
            {"id": "ev-0", "name": "Tap", "type": "SYNCHRONOUS", "status": "TERMINATED"},
        ]
        self.task: str | None = "q01"
        self.verdict = "CORRECT"
        self.submissions: list[dict] = []
        self.network_down = False

    def expire_sessions(self):
        self.sessions.clear()

    def __call__(self, method, url, params=None, body=None):
        if self.network_down:
            raise dres.DresError("timed out")
        path = url.split("://", 1)[1].split("/", 1)[1]
        if path == "api/v2/login":
            if body != {"username": "team07", "password": self.password}:
                return 401, {"status": False, "description": "Invalid credentials"}
            self.logins += 1
            session = f"S{self.logins}"
            self.sessions.add(session)
            return 200, {"id": "u1", "username": "team07", "role": "PARTICIPANT",
                         "sessionId": session}
        if (params or {}).get("session") not in self.sessions:
            return 401, {"status": False, "description": "Unauthorized"}
        if path == "api/v2/client/evaluation/list":
            return 200, self.evaluations
        if path.startswith("api/v2/client/evaluation/currentTask/"):
            if self.task is None:
                return 404, {"status": False, "description": "No active task"}
            return 200, {"name": self.task, "taskGroup": "KIS", "taskType": "KIS", "duration": 300}
        if path.startswith("api/v2/submit/"):
            if body in [s["body"] for s in self.submissions]:
                return 412, {"status": False, "description": "Duplicate submission"}
            self.submissions.append({"evaluation": path.rsplit("/", 1)[1], "body": body})
            return 200, {"status": True, "submission": self.verdict, "description": "ok"}
        return 404, {"status": False, "description": "no route"}


@pytest.fixture()
def fake(monkeypatch):
    server = FakeDres()
    monkeypatch.setattr(dres, "_http", server)
    # Không để _load_meta() nạp keyframe_metadata.json thật đè lên bảng giả.
    monkeypatch.setattr(preprocess, "_meta_loaded", True)
    monkeypatch.setattr(preprocess, "_video_frames", {
        "L21_V001": [{"name": "L21_V001-0001-3000.jpg", "fps": FPS, "frame_idx": 3000}],
        "N001-V001": [{"name": "N001-V001-0001-10.jpg", "fps": 25.0, "frame_idx": 10}],
    })
    return server


def _user(conn, username, role):
    return conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) VALUES (?, ?, ?, 'x', 0, 0, ?)",
        (username, username, role, utcnow_iso()),
    ).lastrowid


@pytest.fixture()
def people(conn):
    admin = _user(conn, "admin", "admin")
    member = _user(conn, "vanh", "member")
    row = lambda uid: conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()  # noqa: E731
    return row(admin), row(member)


@pytest.fixture()
def configured(conn, fake, people):
    router.put_config(router.ConfigIn(username="team07", password="pw"), people[0], conn)
    return people


def _propose(conn, user, **kw):
    kw.setdefault("task_type", "kis")
    kw.setdefault("video_id", "L21_V001")
    return router.propose(router.ProposalIn(**kw), user, conn)


def _status_code(fn, *args, **kwargs):
    with pytest.raises(HTTPException) as e:
        fn(*args, **kwargs)
    return e.value.status_code


# ── tài khoản ────────────────────────────────────────────────────────────────


def test_wrong_password_saves_nothing(conn, fake, people):
    bad = router.ConfigIn(username="team07", password="sai")
    assert _status_code(router.put_config, bad, people[0], conn) == 400
    assert router._config(conn) is None


def test_config_logs_in_picks_the_active_evaluation_and_hides_the_password(conn, configured):
    status = router.get_status(configured[1], conn)
    assert status["logged_in"] is True
    assert status["evaluation_id"] == "ev-1"
    assert "pw" not in json.dumps(status)


def test_blank_password_keeps_the_stored_one(conn, fake, configured):
    router.put_config(router.ConfigIn(username="team07", password=""), configured[0], conn)
    assert router._config(conn)["password"] == "pw"


def test_two_active_evaluations_are_not_guessed(conn, fake, people):
    fake.evaluations[1]["status"] = "ACTIVE"
    router.put_config(router.ConfigIn(username="team07", password="pw"), people[0], conn)
    assert router._config(conn)["evaluation_id"] is None
    assert _status_code(_propose, conn, people[1], frames=[3000]) == 409


# ── định dạng chuỗi nộp ──────────────────────────────────────────────────────


def test_payload_formats_follow_the_btc_document():
    kis = dres.build_payload("kis", "L21_V001", [100100], [3000], None)
    assert kis == {"answerSets": [{"answers": [
        {"mediaItemName": "L21_V001", "start": 100100, "end": 100100}]}]}
    qa = dres.build_payload("qa", "L21_V001", [100100], [3000], "mau xanh")
    assert qa["answerSets"][0]["answers"][0]["text"] == "QA-mau xanh-L21_V001-100100"
    tr = dres.build_payload("trake", "L21_V001", [1, 2, 3], [30, 60, 90], None)
    assert tr["answerSets"][0]["answers"][0]["text"] == "TR-L21_V001-30,60,90"


def test_hyphenated_video_ids_are_flagged():
    assert any("N001-V001" in w for w in dres.warnings_for("qa", "N001-V001", "x"))
    assert dres.warnings_for("kis", "N001-V001", None) == []


# ── đề xuất ──────────────────────────────────────────────────────────────────


def test_frame_and_time_are_converted_with_the_btc_fps(conn, configured):
    row = _propose(conn, configured[1], frames=[3000])
    assert row["times_ms"] == [round(3000 / FPS * 1000)] == [100100]
    assert row["payload"]["answerSets"][0]["answers"][0]["start"] == 100100
    assert row["status"] == "proposed" and row["dres_task_name"] == "q01"
    row = _propose(conn, configured[1], task_type="trake", times_ms=[1000, 2000])
    assert row["frames"] == [30, 60]


def test_unknown_video_is_refused_instead_of_guessing_fps(conn, configured):
    assert _status_code(_propose, conn, configured[1], video_id="L99_V999", frames=[1]) == 400


@pytest.mark.parametrize("kw", [
    {"frames": [1, 2]},                               # KIS chỉ một mốc
    {"frames": [1], "times_ms": [1]},                 # gửi cả hai
    {},                                               # không gửi gì
    {"task_type": "qa", "frames": [1]},               # QA thiếu đáp án
    {"task_type": "qa", "frames": [1], "answer": "a\nb"},
    {"task_type": "trake", "frames": [30, 30]},       # TRAKE trùng mốc
    {"frames": [-1]},
    {"video_id": "L21 V001", "frames": [1]},
])
def test_malformed_proposals_are_refused(conn, configured, kw):
    assert _status_code(_propose, conn, configured[1], **kw) == 400


def test_the_same_answer_cannot_be_proposed_twice_for_one_task(conn, fake, configured):
    admin, member = configured
    first = _propose(conn, member, frames=[3000])
    assert _status_code(_propose, conn, admin, frames=[3000]) == 409
    router.reject(first["id"], admin, conn)
    _propose(conn, member, frames=[3000])            # bị từ chối rồi thì đề xuất lại được
    fake.task = "q02"
    _propose(conn, member, frames=[3000])            # câu khác thì không phải trùng


# ── duyệt và gửi ─────────────────────────────────────────────────────────────


def test_approve_sends_exactly_the_stored_payload(conn, fake, configured):
    admin, member = configured
    row = _propose(conn, member, task_type="qa", frames=[3000], answer="mau xanh")
    sent = router.approve(row["id"], admin, conn, force=False)
    assert sent["status"] == "sent" and sent["verdict"] == "CORRECT"
    assert sent["reviewed_by_name"] == "admin" and sent["proposed_by_name"] == "vanh"
    assert fake.submissions == [{"evaluation": "ev-1", "body": row["payload"]}]


def test_double_approve_sends_once(conn, fake, configured):
    admin, member = configured
    row = _propose(conn, member, frames=[3000])
    router.approve(row["id"], admin, conn, force=False)
    assert _status_code(router.approve, row["id"], admin, conn, force=False) == 409
    assert _status_code(router.reject, row["id"], admin, conn) == 409
    assert len(fake.submissions) == 1


def test_a_proposal_for_the_previous_task_is_not_sent(conn, fake, configured):
    admin, member = configured
    row = _propose(conn, member, frames=[3000])
    fake.task = "q02"
    assert _status_code(router.approve, row["id"], admin, conn, force=False) == 409
    fake.task = None
    assert _status_code(router.approve, row["id"], admin, conn, force=False) == 409
    assert fake.submissions == []
    assert router.approve(row["id"], admin, conn, force=True)["status"] == "sent"


def test_expired_session_logs_in_again_once(conn, fake, configured):
    admin, member = configured
    row = _propose(conn, member, frames=[3000])
    fake.expire_sessions()
    logins = fake.logins
    assert router.approve(row["id"], admin, conn, force=False)["status"] == "sent"
    assert fake.logins == logins + 1


def test_network_failure_is_recorded_and_can_be_retried(conn, fake, configured):
    admin, member = configured
    row = _propose(conn, member, frames=[3000])
    fake.network_down = True
    failed = router.approve(row["id"], admin, conn, force=False)
    assert failed["status"] == "failed" and "timed out" in failed["error"]
    fake.network_down = False
    assert router.approve(row["id"], admin, conn, force=False)["status"] == "sent"
    assert len(fake.submissions) == 1


def test_dres_refusal_keeps_its_description(conn, fake, configured):
    admin, member = configured
    row = _propose(conn, member, frames=[3000])
    fake.submissions.append({"evaluation": "ev-1", "body": row["payload"]})  # DRES đã có bài này
    refused = router.approve(row["id"], admin, conn, force=False)
    assert refused["status"] == "failed" and refused["http_status"] == 412
    assert refused["error"] == "Duplicate submission"


def test_wrong_verdict_is_stored(conn, fake, configured):
    admin, member = configured
    fake.verdict = "WRONG"
    row = _propose(conn, member, frames=[3000])
    assert router.approve(row["id"], admin, conn, force=False)["verdict"] == "WRONG"
    listed = router.list_submissions(member, conn, limit=50)["submissions"]
    assert [s["id"] for s in listed] == [row["id"]]


def test_account_evaluation_and_mode_are_admin_only():
    # Duyệt/từ chối không còn nằm ở đây: quyền của chúng tuỳ submit_mode, xem
    # các test chế độ nộp bên dưới.
    from app.auth.deps import require_admin
    for route in router.router.routes:
        if route.path.endswith(("/config", "/evaluation", "/evaluations", "/submit-mode")):
            deps = [d.call for d in route.dependant.dependencies]
            assert require_admin in deps, route.path


# ── chế độ nộp ───────────────────────────────────────────────────────────────


def _mode(conn, admin, mode):
    return router.put_submit_mode(router.SubmitModeIn(mode=mode), admin, conn)


def test_default_mode_is_admin_only_and_members_cannot_send(conn, fake, configured):
    admin, member = configured
    assert router.get_status(member, conn)["submit_mode"] == "admin_only"
    row = _propose(conn, member, frames=[3000])
    assert _status_code(router.approve, row["id"], member, conn, force=False) == 403
    assert _status_code(router.reject, row["id"], member, conn) == 403
    assert fake.submissions == []
    assert router._load_row(conn, row["id"])["status"] == "proposed"  # 403 không chiếm dòng


def test_everyone_mode_lets_a_member_send_their_own_find(conn, fake, configured):
    admin, member = configured
    assert _mode(conn, admin, "everyone")["submit_mode"] == "everyone"
    row = _propose(conn, member, frames=[3000])
    sent = router.approve(row["id"], member, conn, force=False)
    assert sent["status"] == "sent" and sent["reviewed_by_name"] == "vanh"
    other = _propose(conn, member, task_type="qa", frames=[3000], answer="x")
    assert router.reject(other["id"], member, conn)["status"] == "rejected"
    # Các lớp chặn vẫn giữ nguyên ở chế độ này.
    assert _status_code(router.approve, row["id"], member, conn, force=False) == 409
    assert len(fake.submissions) == 1


def test_switching_back_to_admin_only_takes_effect_at_once(conn, fake, configured):
    admin, member = configured
    _mode(conn, admin, "everyone")
    row = _propose(conn, member, frames=[3000])
    _mode(conn, admin, "admin_only")
    assert _status_code(router.approve, row["id"], member, conn, force=False) == 403
    assert fake.submissions == []


def test_mode_changes_are_audited_once(conn, fake, configured):
    admin, _ = configured
    _mode(conn, admin, "everyone")
    _mode(conn, admin, "everyone")  # không đổi gì thì không ghi
    _mode(conn, admin, "admin_only")
    rows = conn.execute("SELECT summary, detail FROM audit_log WHERE action = 'dres.submit_mode' "
                        "ORDER BY id").fetchall()
    assert [json.loads(r["detail"])["to"] for r in rows] == ["everyone", "admin_only"]
    assert "mọi người nộp được" in rows[0]["summary"]


def test_mode_needs_an_account_first(conn, fake, people):
    assert _status_code(_mode, conn, people[0], "everyone") == 409
