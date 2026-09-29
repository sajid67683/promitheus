"""Transactional email via Resend's HTTP API (no SDK needed)."""
import html
import logging

import requests

from backend.config import settings

logger = logging.getLogger(__name__)


def send_password_reset(to: str, username: str, link: str) -> None:
    if not settings.email_enabled:
        # Local development: print the link instead of sending mail.
        logger.warning("Email is not configured; password reset link for %s: %s", to, link)
        return

    body = f"""
    <div style="font-family:Lexend,Arial,sans-serif;max-width:480px;margin:auto;color:#0f2926">
      <h2 style="margin:0 0 12px">Reset your Promitheus password</h2>
      <p>Hi {html.escape(username)}, someone (hopefully you) asked to reset your password.</p>
      <p><a href="{html.escape(link)}" style="display:inline-block;background:#0f766e;color:#fff;
         padding:12px 20px;border-radius:12px;text-decoration:none;font-weight:600">Choose a new password</a></p>
      <p style="color:#4a5d5a;font-size:14px">This link expires in 1 hour. If you didn't ask for it, ignore this email.</p>
    </div>
    """
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.email_from, "to": [to], "subject": "Reset your Promitheus password", "html": body},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException:
        # Never reveal delivery problems to the requester (it would leak which emails exist).
        logger.exception("Password reset email failed to send")
