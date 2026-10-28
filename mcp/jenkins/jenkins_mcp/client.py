"""Jenkins REST client (JSON API plus the few text/XML endpoints Jenkins serves)."""
from __future__ import annotations

import re
from urllib.parse import quote

import httpx


class JenkinsApiError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Jenkins API error {status_code}: {message}")


def job_path(full_name: str) -> str:
    """'team/app/main' -> '/job/team/job/app/job/main'. Empty name -> '' (Jenkins root)."""
    segments = [s for s in full_name.strip("/").split("/") if s]
    for segment in segments:
        if segment in (".", ".."):
            raise ValueError(f"Invalid job name segment: {segment!r}")
    return "".join(f"/job/{quote(s, safe='')}" for s in segments)


def build_path(job_name: str, build_number: int | None = None) -> str:
    """Path of one build; the last build when no number is given."""
    ref = "lastBuild" if build_number is None else str(int(build_number))
    return f"{job_path(job_name)}/{ref}"


def _extract_error_message(resp: httpx.Response) -> str:
    text = re.sub(r"<(script|style).*?</\1>", " ", resp.text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300] or resp.reason_phrase


class JenkinsClient:
    def __init__(
        self,
        base_url: str,
        authorization: str,
        ssl_verify: bool = True,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": authorization, "Accept": "application/json"},
            verify=ssl_verify,
            timeout=timeout,
            transport=transport,
        )
        self._crumb: tuple[str, str] | None = None
        self._crumb_loaded = False

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise JenkinsApiError(resp.status_code, _extract_error_message(resp))

    def get_json(self, path: str, tree: str | None = None, **params) -> dict | list:
        if tree:
            params["tree"] = tree
        resp = self._http.get(f"{path}/api/json", params=params)
        self._raise_for_status(resp)
        return resp.json()

    def get_json_at(self, path: str) -> dict | list:
        """GET a JSON endpoint that isn't the standard '<object>/api/json' (e.g. wfapi)."""
        resp = self._http.get(path)
        self._raise_for_status(resp)
        return resp.json()

    def get_text(self, path: str, **params) -> str:
        resp = self._http.get(path, params=params, headers={"Accept": "*/*"})
        self._raise_for_status(resp)
        return resp.text

    def get_bytes(self, path: str) -> tuple[bytes, str]:
        resp = self._http.get(path, headers={"Accept": "*/*"})
        self._raise_for_status(resp)
        return resp.content, resp.headers.get("content-type", "")

    def get_version(self) -> str | None:
        resp = self._http.get("/api/json", params={"tree": "mode"})
        self._raise_for_status(resp)
        return resp.headers.get("X-Jenkins")

    def _crumb_header(self) -> dict[str, str]:
        """Best-effort CSRF crumb; Jenkins with crumbs disabled just returns 404."""
        if not self._crumb_loaded:
            self._crumb_loaded = True
            try:
                resp = self._http.get("/crumbIssuer/api/json")
                if resp.status_code == 200:
                    body = resp.json()
                    self._crumb = (body["crumbRequestField"], body["crumb"])
            except (httpx.HTTPError, ValueError, KeyError):
                self._crumb = None
        return {self._crumb[0]: self._crumb[1]} if self._crumb else {}

    def post(
        self,
        path: str,
        params: dict | None = None,
        data: dict | None = None,
        content: str | None = None,
        content_type: str | None = None,
    ) -> httpx.Response:
        headers = self._crumb_header()
        if content_type:
            headers["Content-Type"] = content_type
        resp = self._http.post(
            path,
            params=params,
            data=data,
            content=content.encode("utf-8") if content is not None else None,
            headers=headers,
        )
        self._raise_for_status(resp)
        return resp
