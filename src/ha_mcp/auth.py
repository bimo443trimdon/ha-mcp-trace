"""Static API-key bearer authentication for the HTTP transports."""

import hmac

from fastmcp.server.auth import AccessToken, TokenVerifier


class ApiKeyVerifier(TokenVerifier):
    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._api_key = api_key.encode()

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token or not hmac.compare_digest(token.encode(), self._api_key):
            return None
        return AccessToken(token=token, client_id="api-key", scopes=[], expires_at=None)
