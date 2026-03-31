#!/usr/bin/env python3
"""
OSS RAG Stack — End-to-End Smoke Test Agent

Tests all capabilities against a running stack, including auth-protected endpoints.

Usage:
    python scripts/smoke_test.py                        # defaults to localhost:8000
    python scripts/smoke_test.py --base-url http://localhost:8000
    python scripts/smoke_test.py --skip-chat            # skip the LLM call (no API key needed)

Exit code: 0 if all tests pass, 1 if any fail.

What it tests
─────────────
  1. Liveness          GET  /health                → {status: ok}
  2. Readiness         GET  /health/ready          → {status: ready, vector_store: ...}
  3. Auth              POST /auth/register + login → JWT token
  4. Sessions list     GET  /sessions              → list (auth required)
  5. Profile           GET  /profile + PUT /profile → round-trip
  6. Portfolio CRUD    POST /portfolio/positions   → add; GET /portfolio; DELETE
  7. Chat stream       POST /chat/stream           → SSE events (optional, needs API key)
  8. Feedback          POST /messages/{id}/feedback → 204
  9. Persistence       GET  /sessions/{id}/messages → feedback persisted
 10. Cleanup           DELETE /sessions/{id}        → 204
"""

import argparse
import json
import sys
import time
import uuid
from typing import Any

import httpx

# ── ANSI colours ──────────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ok(label: str, detail: str = "") -> None:
    suffix = f"  {CYAN}{detail}{RESET}" if detail else ""
    print(f"  {GREEN}✓{RESET}  {label}{suffix}")


def fail(label: str, detail: str = "") -> None:
    suffix = f"\n      {RED}{detail}{RESET}" if detail else ""
    print(f"  {RED}✗{RESET}  {label}{suffix}")


def skip(label: str, reason: str = "") -> None:
    suffix = f"  ({reason})" if reason else ""
    print(f"  {YELLOW}–{RESET}  {label}{suffix}")


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")


# ── Test runner ───────────────────────────────────────────────────────────────


class SmokeTest:
    def __init__(self, base_url: str, skip_chat: bool) -> None:
        self.base = base_url.rstrip("/")
        self.skip_chat = skip_chat
        self.client = httpx.Client(base_url=self.base, timeout=60.0)
        self.failures: list[str] = []
        self._token: str | None = None

    def _assert(self, label: str, condition: bool, detail: str = "") -> bool:
        if condition:
            ok(label, detail)
        else:
            fail(label, detail)
            self.failures.append(label)
        return condition

    def _auth_headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    # ── Individual checks ─────────────────────────────────────────────────────

    def check_liveness(self) -> None:
        section("1. Liveness  GET /health")
        r = self.client.get("/health")
        self._assert("status 200", r.status_code == 200, f"got {r.status_code}")
        body = r.json()
        self._assert("body = {status: ok}", body == {"status": "ok"}, str(body))

    def check_readiness(self) -> None:
        section("2. Readiness  GET /health/ready")
        r = self.client.get("/health/ready")
        self._assert("status 200", r.status_code == 200, f"got {r.status_code}")
        body = r.json()
        self._assert('body.status == "ready"', body.get("status") == "ready", str(body))
        self._assert('"vector_store" key present', "vector_store" in body, str(body))
        vs = body.get("vector_store", {})
        self._assert('"vector_store.status" present', "status" in vs, str(vs))

    def check_auth(self) -> bool:
        """Register (idempotent) + login → store JWT token. Returns True on success."""
        section("3. Auth  POST /auth/register + /auth/login")

        # Use a stable email so repeated runs don't accumulate junk users
        email = "smoke-test@example.com"
        password = "smoke-test-password-123"

        reg = self.client.post(
            "/auth/register",
            json={"email": email, "password": password, "display_name": "Smoke Test"},
        )
        if reg.status_code in (200, 201):
            ok("register → token returned")
            self._token = reg.json().get("access_token")
        elif reg.status_code == 409:
            ok("register → 409 (already exists, will log in)")
        else:
            self._assert(
                "register → 200/201/409",
                False,
                f"got {reg.status_code}: {reg.text[:120]}",
            )
            return False

        # Always log in to get a fresh token
        login = self.client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        if not self._assert(
            "login → 200", login.status_code == 200, f"got {login.status_code}"
        ):
            return False

        body = login.json()
        self._token = body.get("access_token")
        user = body.get("user", {})
        self._assert("token present", bool(self._token), "access_token missing")
        self._assert("user.email correct", user.get("email") == email, str(user))

        # Verify GET /auth/me
        me = self.client.get("/auth/me", headers=self._auth_headers())
        self._assert("GET /auth/me → 200", me.status_code == 200, f"got {me.status_code}")

        return bool(self._token)

    def check_sessions_list(self) -> list[dict]:
        section("4. Sessions list  GET /sessions")
        r = self.client.get("/sessions", headers=self._auth_headers())
        self._assert("status 200", r.status_code == 200, f"got {r.status_code}")
        data = r.json()
        self._assert("response is a list", isinstance(data, list), type(data).__name__)
        ok(f"found {len(data)} existing session(s)")
        return data

    def check_profile(self) -> None:
        section("5. Investor Profile  GET + PUT /profile")
        # GET — may be empty defaults
        r = self.client.get("/profile", headers=self._auth_headers())
        self._assert("GET /profile → 200", r.status_code == 200, f"got {r.status_code}")

        # PUT — save some data
        payload = {
            "age": 45,
            "risk_tolerance": 3,
            "horizon_years": 20,
            "goals": ["retirement", "growth"],
        }
        r2 = self.client.put("/profile", json=payload, headers=self._auth_headers())
        self._assert("PUT /profile → 200", r2.status_code == 200, f"got {r2.status_code}")
        saved = r2.json()
        self._assert("age persisted", saved.get("age") == 45, str(saved))
        self._assert("risk_tolerance persisted", saved.get("risk_tolerance") == 3, str(saved))

    def check_portfolio_crud(self) -> str | None:
        """Add a position, list, delete. Returns position id for cleanup confirmation."""
        section("6. Portfolio CRUD  /portfolio")

        # Add position
        add = self.client.post(
            "/portfolio/positions",
            json={
                "ticker": "SMOKE",
                "asset_type": "stock",
                "shares": 10.0,
                "avg_cost_usd": 99.99,
                "notes": "smoke test position",
            },
            headers=self._auth_headers(),
        )
        if not self._assert(
            "POST /portfolio/positions → 200/201",
            add.status_code in (200, 201),
            f"got {add.status_code}: {add.text[:120]}",
        ):
            return None

        position = add.json()
        position_id = position.get("id")
        self._assert("ticker correct", position.get("ticker") == "SMOKE", str(position))
        self._assert("id present", bool(position_id), "id missing from response")

        # List
        lst = self.client.get("/portfolio", headers=self._auth_headers())
        self._assert("GET /portfolio → 200", lst.status_code == 200, f"got {lst.status_code}")
        positions = lst.json()
        found = any(p.get("ticker") == "SMOKE" for p in positions)
        self._assert("SMOKE position in list", found, f"{len(positions)} positions returned")

        # Delete
        if position_id:
            delete = self.client.delete(
                f"/portfolio/positions/{position_id}",
                headers=self._auth_headers(),
            )
            self._assert(
                "DELETE /portfolio/positions/{id} → 204",
                delete.status_code == 204,
                f"got {delete.status_code}",
            )

        return position_id

    def check_feedback_errors(self) -> None:
        section("7. Feedback error cases")
        # Invalid UUID
        r = self.client.post(
            "/messages/not-a-uuid/feedback",
            json={"value": "up"},
            headers=self._auth_headers(),
        )
        self._assert(
            "invalid UUID → 400/422",
            r.status_code in (400, 422),
            f"got {r.status_code}",
        )
        # Nonexistent message
        fake = "00000000-0000-0000-0000-000000000099"
        r = self.client.post(
            f"/messages/{fake}/feedback",
            json={"value": "up"},
            headers=self._auth_headers(),
        )
        self._assert(
            "nonexistent message → 404",
            r.status_code == 404,
            f"got {r.status_code}",
        )
        # Invalid value
        r = self.client.post(
            f"/messages/{fake}/feedback",
            json={"value": "meh"},
            headers=self._auth_headers(),
        )
        self._assert(
            'invalid value ("meh") → 422',
            r.status_code == 422,
            f"got {r.status_code}",
        )

    def check_chat_and_feedback(self) -> str | None:
        """
        Streams a chat message, captures session_id + message_id,
        submits feedback, then verifies persistence.
        Returns the session_id so the caller can clean it up.
        """
        section("8. Chat stream  POST /chat/stream")

        payload = {
            "message": "In one sentence, what is a P/E ratio?",
            "rewrite_query": False,
            "mode": "expert_context",
        }

        session_id: str | None = None
        message_id: str | None = None
        got_delta = False
        got_done = False
        full_text = ""

        try:
            with self.client.stream(
                "POST",
                "/chat/stream",
                json=payload,
                headers={
                    "Accept": "text/event-stream",
                    **self._auth_headers(),
                },
                timeout=90.0,
            ) as r:
                if not self._assert(
                    "stream opened (200)",
                    r.status_code == 200,
                    f"got {r.status_code}",
                ):
                    return None

                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if not raw:
                        continue
                    try:
                        event: dict[str, Any] = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    etype = event.get("type")
                    if etype == "session":
                        session_id = event.get("session_id")
                        message_id = event.get("message_id")
                    elif etype == "delta":
                        got_delta = True
                        full_text += event.get("text", "")
                    elif etype == "done":
                        got_done = True
                    elif etype == "error":
                        self._assert(
                            "no stream error",
                            False,
                            event.get("message", "unknown error"),
                        )
                        return session_id

        except httpx.ReadTimeout:
            self._assert("stream completed within timeout", False, "ReadTimeout after 90s")
            return session_id

        self._assert("received session event", session_id is not None, "session_id missing")
        self._assert("received message_id", message_id is not None, "message_id missing")
        self._assert("received delta tokens", got_delta, "no delta events")
        self._assert("received done event", got_done, "no done event")
        if full_text:
            preview = full_text[:80].replace("\n", " ")
            ok(f'response preview: "{preview}…"')

        if not session_id or not message_id:
            return session_id

        # ── Feedback round-trip ────────────────────────────────────────────
        section("9. Feedback round-trip")

        r2 = self.client.post(
            f"/messages/{message_id}/feedback",
            json={"value": "up"},
            headers=self._auth_headers(),
        )
        self._assert(
            "thumbs-up → 204",
            r2.status_code == 204,
            f"got {r2.status_code}",
        )

        r3 = self.client.post(
            f"/messages/{message_id}/feedback",
            json={"value": "down"},
            headers=self._auth_headers(),
        )
        self._assert(
            "overwrite with thumbs-down → 204",
            r3.status_code == 204,
            f"got {r3.status_code}",
        )

        r4 = self.client.get(
            f"/sessions/{session_id}/messages",
            headers=self._auth_headers(),
        )
        self._assert(
            "GET /sessions/{id}/messages → 200",
            r4.status_code == 200,
            f"got {r4.status_code}",
        )
        msgs = r4.json()
        target = next((m for m in msgs if m.get("id") == message_id), None)
        self._assert(
            "message found in session messages",
            target is not None,
            f"message_id={message_id} not in list of {len(msgs)}",
        )
        if target:
            self._assert(
                'feedback persisted as "down"',
                target.get("feedback") == "down",
                f'got {target.get("feedback")!r}',
            )
            self._assert(
                "feedback_at is set",
                target.get("feedback_at") is not None,
                f'got {target.get("feedback_at")!r}',
            )

        return session_id

    def check_session_delete(self, session_id: str) -> None:
        section("10. Session cleanup  DELETE /sessions/{id}")
        r = self.client.delete(
            f"/sessions/{session_id}",
            headers=self._auth_headers(),
        )
        self._assert("DELETE → 204", r.status_code == 204, f"got {r.status_code}")
        r2 = self.client.get(
            f"/sessions/{session_id}",
            headers=self._auth_headers(),
        )
        self._assert("session gone → 404", r2.status_code == 404, f"got {r2.status_code}")

    # ── Main runner ───────────────────────────────────────────────────────────

    def run(self) -> int:
        width = 60
        print(f"\n{BOLD}{'─' * width}{RESET}")
        print(f"{BOLD}  OSS RAG Stack — Smoke Test Agent{RESET}")
        print(f"  Target: {CYAN}{self.base}{RESET}")
        print(f"{'─' * width}{RESET}")

        t0 = time.monotonic()

        self.check_liveness()
        self.check_readiness()

        auth_ok = self.check_auth()
        if not auth_ok:
            print(f"\n{RED}{BOLD}  Auth failed — remaining tests require a valid token{RESET}\n")
            return 1

        self.check_sessions_list()
        self.check_profile()
        self.check_portfolio_crud()
        self.check_feedback_errors()

        created_session: str | None = None
        if self.skip_chat:
            section("8–9. Chat + feedback")
            skip("chat stream", "skipped via --skip-chat")
            skip("feedback round-trip", "skipped (no chat)")
            section("10. Session cleanup")
            skip("session delete", "skipped (no session created)")
        else:
            created_session = self.check_chat_and_feedback()
            if created_session:
                self.check_session_delete(created_session)

        # ── Summary ───────────────────────────────────────────────────────
        elapsed = time.monotonic() - t0
        print(f"\n{'─' * width}")
        if self.failures:
            print(
                f"{RED}{BOLD}  FAILED{RESET}  "
                f"{len(self.failures)} check(s) failed  ({elapsed:.1f}s)"
            )
            for f in self.failures:
                print(f"    {RED}✗{RESET}  {f}")
            print()
            return 1
        else:
            print(f"{GREEN}{BOLD}  ALL CHECKS PASSED{RESET}  ({elapsed:.1f}s)")
            print()
            return 0


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="OSS RAG smoke test agent")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8010",
        help="Backend base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--skip-chat",
        action="store_true",
        help="Skip the chat stream test (no Anthropic API call, faster)",
    )
    args = parser.parse_args()

    runner = SmokeTest(base_url=args.base_url, skip_chat=args.skip_chat)
    sys.exit(runner.run())


if __name__ == "__main__":
    main()
