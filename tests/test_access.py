from __future__ import annotations

import time

from access.hmac_auth import sign, verify
from access.screening import PrivacyScreener
from access.store import AccessStore


def test_user_and_scope_group_crud(settings):
    store = AccessStore(settings)

    user = store.create_user("Alice", "alice@example.com", is_admin=True)
    assert user["id"].startswith("usr_")
    assert user["api_key"].startswith("pkb_")
    assert user["is_admin"] is True

    got = store.get_user(user["id"])
    assert got and got["name"] == "Alice"

    by_key = store.get_user_by_api_key(user["api_key"])
    assert by_key and by_key["id"] == user["id"]
    assert store.get_user_by_api_key("nope") is None
    assert store.get_user_by_api_key("") is None

    listed = store.list_users()
    assert any(u["id"] == user["id"] for u in listed)

    group = store.create_scope_group("team-a", topics=["python", "ai"], users=[user["id"]])
    assert group["id"].startswith("sg_")
    assert group["topics"] == ["python", "ai"]
    assert group["users"] == [user["id"]]

    got_group = store.get_scope_group(group["id"])
    assert got_group and got_group["name"] == "team-a"

    updated = store.update_scope_group(group["id"], topics=["rag"], name="team-b")
    assert updated and updated["topics"] == ["rag"] and updated["name"] == "team-b"

    groups = store.list_scope_groups()
    assert any(g["id"] == group["id"] for g in groups)


def test_client_registration(settings):
    store = AccessStore(settings)
    client = store.register_client("bot", "https://example.com/cb")
    assert client["client_id"].startswith("cli_")
    assert client["hmac_secret"]
    assert client["callback_url"] == "https://example.com/cb"

    got = store.get_client(client["client_id"])
    assert got and got["name"] == "bot"

    clients = store.list_clients()
    assert any(c["client_id"] == client["client_id"] for c in clients)


def test_request_grant_flow(settings):
    store = AccessStore(settings)
    client = store.register_client("bot")
    user = store.create_user("Bob")

    req = store.create_request(client["client_id"], user["id"], "notes.read", "for testing")
    assert req["status"] == "pending"

    reqs = store.list_requests(user_id=user["id"])
    assert any(r["id"] == req["id"] for r in reqs)

    pending = store.list_requests(status="pending")
    assert any(r["id"] == req["id"] for r in pending)

    store.update_request(req["id"], status="approved")
    assert store.get_request(req["id"])["status"] == "approved"

    grant = store.create_grant(
        req["id"], client["client_id"], user["id"], "notes.read", ttl_days=7
    )
    assert grant["expires_at"]
    assert grant["id"].startswith("grt_")

    grants = store.list_grants(user_id=user["id"])
    assert any(g["id"] == grant["id"] for g in grants)
    grants_by_client = store.list_grants(client_id=client["client_id"])
    assert any(g["id"] == grant["id"] for g in grants_by_client)

    store.revoke_grant(grant["id"])
    assert store.get_grant(grant["id"]) is None


def test_hmac_sign_verify_roundtrip():
    secret = "top-secret"
    method = "POST"
    path = "/access/requests"
    body = '{"scope":"notes.read"}'
    ts = str(int(time.time()))

    sig = sign(secret, method, path, ts, body)
    assert verify(secret, method, path, ts, body, sig) is True

    # Wrong secret
    assert verify("other-secret", method, path, ts, body, sig) is False

    # Old timestamp
    old_ts = str(int(time.time()) - 10000)
    old_sig = sign(secret, method, path, old_ts, body)
    assert verify(secret, method, path, old_ts, body, old_sig, max_skew_seconds=300) is False

    # Invalid timestamp
    assert verify(secret, method, path, "not-a-time", body, sig) is False


def test_screening_rejects_sensitive_scope():
    screener = PrivacyScreener()
    ok, reason = screener.filter_scope("read user password data", ["salary", "password", "secret"])
    assert ok is False
    assert "password" in reason

    ok2, reason2 = screener.filter_scope("notes.read", ["salary", "password", "secret"])
    assert ok2 is True
    assert reason2 == ""

    # Blacklist topic hit even if not in default keywords
    ok3, reason3 = screener.filter_scope("financial.report", ["financial"])
    assert ok3 is False
    assert "financial" in reason3
