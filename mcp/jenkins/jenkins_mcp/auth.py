"""Per-connection Jenkins authentication — forwards a member's own credentials from request headers."""
from __future__ import annotations

from typing import Mapping

import httpx

from .client import JenkinsClient
from .config import JenkinsConfig

_MISSING_CREDENTIALS_MESSAGE = (
    "Missing or malformed Authorization header; expected 'Basic <base64(user:api_token)>' "
    "or 'Bearer <token>'."
)


class MissingCredentialsError(Exception):
    pass


def resolve_client_from_headers(
    headers: Mapping[str, str],
    base_config: JenkinsConfig,
    transport: httpx.BaseTransport | None = None,
) -> JenkinsClient:
    auth_header = (headers.get("authorization") or "").strip()
    scheme, _, credentials = auth_header.partition(" ")
    if scheme.lower() not in ("basic", "bearer") or not credentials.strip():
        raise MissingCredentialsError(_MISSING_CREDENTIALS_MESSAGE)

    return JenkinsClient(
        base_url=base_config.url,
        authorization=f"{scheme.capitalize()} {credentials.strip()}",
        ssl_verify=base_config.ssl_verify,
        timeout=base_config.timeout,
        transport=transport,
    )
