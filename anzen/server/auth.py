from fastapi import Header, HTTPException, status
from anzen.server.config import settings


async def verify_api_key(x_api_key: str = Header(default="")):
    """Optional API key auth. Disabled if ANZEN_API_KEY is empty."""
    if not settings.api_key:
        return  # Dev mode — no auth
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
