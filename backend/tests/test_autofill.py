import pytest

from app.answers.autofill import spread


def test_alternates_around_the_anchor():
    # R@k is a max over the first k rows, so the closest candidates have to land
    # in the highest ranks.
    assert spread(1745, 25, 6) == [1770, 1720, 1795, 1695, 1820, 1670]


def test_never_returns_a_negative_frame():
    assert all(frame >= 0 for frame in spread(30, 25, 8))


def test_reallocates_the_budget_when_one_side_runs_out():
    frames = spread(30, 25, 6)
    assert len(frames) == 6
    assert len(set(frames)) == 6


def test_returns_nothing_for_a_zero_count():
    assert spread(1745, 25, 0) == []


def test_returns_nothing_for_a_zero_step():
    assert spread(1745, 0, 10) == []


@pytest.mark.parametrize("step", [1, 2, 25, 200])
def test_frames_are_unique_for_any_step(step):
    frames = spread(5000, step, 40)
    assert len(set(frames)) == 40


def test_never_returns_the_anchor_itself():
    assert 1745 not in spread(1745, 25, 20)


def test_trake_default_step_stays_inside_the_scoring_window():
    # The rules put each TRAKE event's window at "usually under 10 frames", so a
    # one-second step would jump straight over it.
    assert spread(4707, 2, 4) == [4709, 4705, 4711, 4703]
