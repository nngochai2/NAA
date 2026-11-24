"""Thin synchronous HTTP client for the ADO Server REST API.

Calls are sync for simplicity; the MCP handlers run them in a worker thread.
"""
from __future__ import annotations

import httpx
from httpx_ntlm import HttpNtlmAuth

from .config import AdoConfig

DEFAULT_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 60


class AdoClient:
    def __init__(
        self,
        base_url: str,
        project: str,
        username: str,
        password: str,
        api_version: str = "5.0",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.project = project
        self.api_version = api_version
        self._username = username
        self._password = password
        self._transport = transport  # injected in tests

    @classmethod
    def from_config(cls, cfg: AdoConfig) -> AdoClient:
        return cls(cfg.base_url, cfg.project, cfg.username, cfg.password, cfg.api_version)

    # ── URLs ──────────────────────────────────────────────────────────────────

    def url(self, path: str) -> str:
        """Build a full API URL under the configured project."""
        return f"{self.base_url}/{self.project}/_apis/{path}"

    def wi_url(self, path: str) -> str:
        return self.url(f"wit/{path}")

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def get(self, url: str, params: dict | None = None) -> dict:
        return self._request("GET", url, params=params).json()

    def post(self, url: str, body: dict, params: dict | None = None) -> dict:
        return self._request("POST", url, params=params, json=body).json()

    def download(self, url: str) -> bytes:
        return self._request("GET", url, timeout=DOWNLOAD_TIMEOUT, json_headers=False).content

    def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        json: dict | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        json_headers: bool = True,
    ) -> httpx.Response:
        # NTLM is connection-oriented, so each call gets its own client
        # (the worker threads never share an authenticated connection).
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        with httpx.Client(
            auth=HttpNtlmAuth(self._username, self._password),
            timeout=timeout,
            verify=False,  # on-prem servers commonly use an internal CA
            transport=self._transport,
        ) as http:
            resp = http.request(
                method,
                url,
                params={"api-version": self.api_version, **(params or {})},
                json=json,
                headers=headers if json_headers else None,
            )
        resp.raise_for_status()
        return resp
