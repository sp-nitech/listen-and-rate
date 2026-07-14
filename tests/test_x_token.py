from __future__ import annotations

from listen_and_rate.x_token import commit, resolve

SECRET = b"test-secret-32-bytes-long-enough"


def test_commit_is_deterministic():
    assert commit("a", "b", "a", SECRET) == commit("a", "b", "a", SECRET)


def test_commit_differs_for_different_matched_id():
    assert commit("a", "b", "a", SECRET) != commit("a", "b", "b", SECRET)


def test_commit_differs_for_different_secret():
    other_secret = b"different-secret-value-32-bytes"
    assert commit("a", "b", "a", SECRET) != commit("a", "b", "a", other_secret)


def test_resolve_recovers_matched_id_a():
    token = commit("id_a", "id_b", "id_a", SECRET)
    assert resolve("id_a", "id_b", token, SECRET) == "id_a"


def test_resolve_recovers_matched_id_b():
    token = commit("id_a", "id_b", "id_b", SECRET)
    assert resolve("id_a", "id_b", token, SECRET) == "id_b"


def test_resolve_returns_none_for_forged_token():
    assert resolve("id_a", "id_b", "not-a-real-token", SECRET) is None


def test_resolve_returns_none_for_wrong_secret():
    token = commit("id_a", "id_b", "id_a", SECRET)
    wrong_secret = b"wrong-secret-should-not-work-32"
    assert resolve("id_a", "id_b", token, wrong_secret) is None


def test_resolve_returns_none_when_token_from_different_pair():
    token = commit("id_x", "id_y", "id_x", SECRET)
    assert resolve("id_a", "id_b", token, SECRET) is None


def test_commit_is_order_independent():
    assert commit("id_a", "id_b", "id_a", SECRET) == commit(
        "id_b", "id_a", "id_a", SECRET
    )


def test_resolve_works_regardless_of_pair_order():
    token = commit("id_a", "id_b", "id_b", SECRET)
    assert resolve("id_b", "id_a", token, SECRET) == "id_b"
