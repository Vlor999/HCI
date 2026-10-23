"""Bearer-token check shared by the API server and the metrics dashboard."""

import secrets

from fastapi import Header, HTTPException

from hci.config import get_settings


def auth(authorization: str = Header("")) -> None:
    """Check the bearer token, comparing bytes so any header value gives 401 on mismatch.

    Args:
        authorization: the `Authorization` header.

    Raises:
        HTTPException: 401 when the token is missing or wrong.
    """
    expected = f"Bearer {get_settings().token}".encode()
    if not secrets.compare_digest(authorization.encode(), expected):
        raise HTTPException(401, "Missing or wrong token. Open the link printed by `hci serve`.")
