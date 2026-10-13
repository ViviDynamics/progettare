"""Installation tokens minted by the App itself, refreshed before they lapse.

The pod holds the App's credentials, so it can mint its own
installation tokens: no human re-minting, no ceremony 401s. GitHub
calls go over stdlib urllib and the JWT is signed with `openssl`
through a subprocess, which keeps the dependency set at the stdlib.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from typing import Any

LIFETIME_SECONDS = 3600.0
REFRESH_MARGIN_SECONDS = 300.0


def _b64url(payload: str | bytes) -> str:
    data = payload.encode() if isinstance(payload, str) else payload
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _openssl_sign(body: str, private_key: str) -> bytes:
    # The body to sign arrives on stdin and the key as a file path: the two
    # cannot share a stream, or what openssl signs is not what GitHub reads.
    fd, key_path = tempfile.mkstemp(suffix=".pem")
    try:
        with os.fdopen(fd, "w") as key_file:
            key_file.write(private_key)
        completed = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=body.encode(),
            capture_output=True,
            check=True,
        )
    finally:
        os.unlink(key_path)
    return completed.stdout


def _github_api(
    method: str, path: str, jwt: str | None = None, body: dict[str, Any] | None = None
) -> Any:
    import urllib.request

    headers = {"Accept": "application/vnd.github+json"}
    if jwt is not None:
        headers["Authorization"] = f"Bearer {jwt}"
    request = urllib.request.Request(
        "https://api.github.com" + path,
        method=method,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


Signer = Callable[[str], bytes]
Api = Callable[[str, str, str | None], Any]


class InstallationAuth:
    """A live installation token for the gh subprocess, refreshed lazily.

    `token()` hands back the cached token while it is fresh and mints a
    new one the moment the clock enters the refresh margin, so a
    ceremony started near a token boundary still gets a live token.
    """

    def __init__(
        self,
        app_id: str,
        private_key: str,
        *,
        sign: Signer | None = None,
        api: Api | None = None,
        clock: Callable[[], float] | None = None,
        lifetime: float = LIFETIME_SECONDS,
        margin: float = REFRESH_MARGIN_SECONDS,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._sign = sign if sign is not None else self._sign_with_openssl
        self._api = api if api is not None else _github_api
        self._clock = clock if clock is not None else time.time
        self._lifetime = lifetime
        self._margin = margin
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at = 0.0

    def token(self) -> str:
        with self._lock:
            now = self._clock()
            if self._token is None or now >= self._expires_at - self._margin:
                self._expires_at = now + self._lifetime
                self._token = self._mint(now)
            return self._token

    def _mint(self, now: float) -> str:
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}))
        payload = _b64url(
            json.dumps(
                {"iss": self._app_id, "iat": int(now) - 60, "exp": int(now) + 540}
            )
        )
        signing_input = f"{header}.{payload}"
        signature = self._sign(signing_input)
        jwt = f"{signing_input}.{_b64url(signature)}"
        installations = self._api("GET", "/app/installations", jwt)
        installation_id = installations[0]["id"]
        minted = self._api(
            "POST", f"/app/installations/{installation_id}/access_tokens", jwt
        )
        return str(minted["token"])

    def _sign_with_openssl(self, body: str) -> bytes:
        return _openssl_sign(body, self._private_key)


def gh_dispatch(
    auth: InstallationAuth | None, runner: Any = None
) -> Callable[[list[str]], None]:
    """The default gh seam, carrying a rotated token when the App's
    credentials are configured; otherwise the environment's own
    `GH_TOKEN` stands."""
    if auth is None:
        return _post_gh

    def dispatch(argv: list[str]) -> None:
        import os

        run = runner if runner is not None else subprocess.run
        run(argv, check=False, env={**os.environ, "GH_TOKEN": auth.token()})

    return dispatch


def _post_gh(argv: list[str]) -> None:
    subprocess.run(argv, check=False)
