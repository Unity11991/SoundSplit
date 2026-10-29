import secrets
import hmac
import hashlib
import time
from typing import Optional
from fastapi import Request, Response, HTTPException, status
from app.core.config import settings

def get_or_create_session_id(request: Request, response: Response) -> str:
    """Retrieve existing session ID from secure HTTP cookie or header, or create a new cryptographically secure one."""
    # 1. Check custom header (passed by frontend)
    session_id = request.headers.get("X-Session-ID")
    if session_id and len(session_id) >= 16:
        return session_id

    # 2. Check query parameter (essential for cross-origin SSE and <audio> streams)
    session_id = request.query_params.get("session_id")
    if session_id and len(session_id) >= 16:
        return session_id

    # 3. Check cookie
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_id:
        session_id = secrets.token_hex(24)
        is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        # Set hardened session cookie (samesite=none + secure=true enables cross-origin requests from Vercel to Render)
        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=session_id,
            httponly=True,
            samesite="none" if is_https else "lax",
            max_age=86400 * 30,  # 30 days
            secure=is_https
        )
    return session_id

def verify_project_ownership(project_session_id: str, current_session_id: str):
    """Enforce strict ownership to prevent IDOR vulnerabilities."""
    if not hmac.compare_digest(project_session_id, current_session_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: You do not have permission to access or modify this project resource."
        )
