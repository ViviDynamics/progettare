"""InstallationAuth: minted from the App's credentials, refreshed before expiry."""

from __future__ import annotations

import base64
import json
from typing import Any

from progettare.auth import InstallationAuth, gh_dispatch

APP_ID = "5280026"


def recording_auth(
    tokens: list[str], mints: list[int], clock: Any
) -> tuple[InstallationAuth, list[tuple[str, str, str | None]]]:
    """An auth wired to offline fakes; calls to GitHub land in `tokens`."""
    calls: list[tuple[str, str, str | None]] = []

    def sign(body: str) -> bytes:
        mints.append(len(mints))
        return b"signature"

    def api(method: str, path: str, jwt: str | None = None) -> Any:
        calls.append((method, path, jwt))
        if method == "GET":
            return [{"id": 170440362}]
        tokens.append(f"tok-{len(tokens) + 1}")
        return {"token": tokens[-1], "expires_at": "2030-01-01T00:00:00Z"}

    auth = InstallationAuth(APP_ID, "KEY", sign=sign, api=api, clock=clock)
    return auth, calls


def test_the_first_call_mints_and_the_next_call_reuses_it() -> None:
    tokens: list[str] = []
    auth, _ = recording_auth(tokens, [], lambda: 1000.0)
    first = auth.token()
    second = auth.token()
    assert first == "tok-1"
    assert second == "tok-1"


def test_a_token_past_its_lifetime_mints_again() -> None:
    tokens: list[str] = []
    time_now = [1000.0]
    auth, _ = recording_auth(tokens, [], lambda: time_now[0])
    auth.token()
    time_now[0] = 1000.0 + 3600.0 + 1.0
    assert auth.token() == "tok-2"


def test_a_token_inside_the_refresh_margin_mints_again() -> None:
    tokens: list[str] = []
    time_now = [1000.0]
    auth, _ = recording_auth(tokens, [], lambda: time_now[0])
    auth.token()
    time_now[0] = 1000.0 + 3600.0 - 200.0
    assert auth.token() == "tok-2"


def test_the_mint_carries_the_app_credentials() -> None:
    mints: list[int] = []
    bodies: list[str] = []
    calls: list[tuple[str, str, str | None]] = []

    def sign(body: str) -> bytes:
        mints.append(len(mints))
        bodies.append(body)
        return b"signature"

    def api(method: str, path: str, jwt: str | None = None) -> Any:
        calls.append((method, path, jwt))
        if method == "GET":
            return [{"id": 170440362}]
        return {"token": "tok-1", "expires_at": "2030-01-01T00:00:00Z"}

    auth = InstallationAuth(APP_ID, "KEY", sign=sign, api=api, clock=lambda: 1000.0)
    auth.token()
    _, payload = bodies[0].split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    assert claims["iss"] == APP_ID
    assert calls[0][0] == "GET"
    assert calls[0][2] is not None
    assert calls[0][2].startswith("eyJ")
    assert calls[1][0] == "POST"
    assert calls[1][1] == "/app/installations/170440362/access_tokens"


def test_the_dispatch_hands_the_gh_subprocess_a_live_token() -> None:
    tokens: list[str] = []
    auth, _ = recording_auth(tokens, [], lambda: 1000.0)
    captured: dict[str, Any] = {}

    def runner(argv: list[str], **kwargs: Any) -> None:
        captured.update(kwargs)

    dispatch = gh_dispatch(auth, runner=runner)
    dispatch(["gh", "api", "repos/o/r/issues/7/comments"])
    assert captured["env"]["GH_TOKEN"] == "tok-1"


def test_the_real_openssl_signer_round_trips(tmp_path: Any) -> None:
    """The shipped signer produces a signature openssl verifies.

    This test exists because the first signer passed the data and the key
    through one unseekable stdin and every minted JWT was garbage, which
    the injected fakes could never see.
    """
    import subprocess

    from progettare.auth import _openssl_sign

    subprocess.run(
        ["openssl", "genrsa", "-out", str(tmp_path / "key.pem"), "2048"],
        check=True,
        capture_output=True,
    )
    private_key = (tmp_path / "key.pem").read_text()
    body = "header.payload"
    signature = _openssl_sign(body, private_key)
    signature_path = tmp_path / "sig.bin"
    signature_path.write_bytes(signature)
    subprocess.run(
        ["openssl", "rsa", "-in", str(tmp_path / "key.pem"), "-pubout", "-out",
         str(tmp_path / "pub.pem")],
        check=True,
        capture_output=True,
    )
    verified = subprocess.run(
        [
            "openssl", "dgst", "-sha256", "-verify", str(tmp_path / "pub.pem"),
            "-signature", str(signature_path),
        ],
        input=body.encode(),
        capture_output=True,
    )
    assert verified.returncode == 0, verified.stderr

    tampered = subprocess.run(
        [
            "openssl", "dgst", "-sha256", "-verify", str(tmp_path / "pub.pem"),
            "-signature", str(signature_path),
        ],
        input=b"header.payloae",
        capture_output=True,
    )
    assert tampered.returncode != 0
    assert signature_path.stat().st_size == 256
