"""Per-connection Jira authentication — resolves a member's own PAT from request headers."""
from __future__ import annotations

from typing import Mapping

import httpx

from .client import JiraClient
from .config import JiraConfig

_MISSING_CREDENTIALS_MESSAGE = "Missing or malformed Authorization header; expected 'Bearer <PAT>'."


class MissingCredentialsError(Exception):
    pass


def resolve_client_from_headers(
    headers: Mapping[str, str],
    base_config: JiraConfig,
    transport: httpx.BaseTransport | None = None,
) -> JiraClient:
    auth_header = headers.get("authorization") or ""
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise MissingCredentialsError(_MISSING_CREDENTIALS_MESSAGE)

    return JiraClient(
        base_url=base_config.url, token=token.strip(), ssl_verify=base_config.ssl_verify, transport=transport
    )
