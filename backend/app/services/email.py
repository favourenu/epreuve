"""Transactional email via Resend (https://resend.com).

Without RESEND_API_KEY (local development), emails are written to the log
instead of being sent, so flows like password reset still work end to end.
"""

import html
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


class EmailError(Exception):
    pass


@dataclass
class Email:
    to: str
    subject: str
    html: str
    text: str


class EmailSender(Protocol):
    def send(self, email: Email) -> None: ...


@dataclass
class ResendSender:
    api_key: str
    from_address: str
    timeout: float = 15.0

    def send(self, email: Email) -> None:
        try:
            resp = httpx.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "from": self.from_address,
                    "to": [email.to],
                    "subject": email.subject,
                    "html": email.html,
                    "text": email.text,
                },
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise EmailError(f"Resend request failed: {type(exc).__name__}") from exc
        if resp.status_code >= 300:
            raise EmailError(f"Resend returned HTTP {resp.status_code}: {resp.text[:300]}")


class LogSender:
    """Development fallback: print the email instead of sending it."""

    def send(self, email: Email) -> None:
        log.warning("RESEND_API_KEY is not set; email not sent. To: %s | %s\n%s", email.to, email.subject, email.text)


@lru_cache
def get_email_sender() -> EmailSender:
    s = get_settings()
    if s.resend_api_key:
        return ResendSender(s.resend_api_key, s.email_from)
    return LogSender()


def password_reset_email(to: str, name: str, link: str, minutes: int) -> Email:
    first = html.escape(name.split(" ")[0]) if name.strip() else "there"
    safe_link = html.escape(link, quote=True)
    text = (
        f"Hi {name.split(' ')[0] or 'there'},\n\n"
        f"Someone (hopefully you) asked to reset the password for your Épreuve account.\n\n"
        f"Reset it here (the link works once and expires in {minutes} minutes):\n{link}\n\n"
        "If you didn't ask for this, you can ignore this email. Your password won't change.\n\n"
        "Épreuve"
    )
    body = f"""<!doctype html>
<html lang="en">
<body style="margin:0;padding:0;background:#f6f2ea;font-family:Arial,Helvetica,sans-serif;color:#1c1b18;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f2ea;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#fffdf8;border:1px solid #e2dbcc;border-radius:14px;">
        <tr><td style="padding:28px 28px 8px;">
          <span style="display:inline-block;background:#145c4a;color:#fffdf8;font-weight:bold;border-radius:8px;padding:4px 10px;font-size:18px;">É</span>
          <span style="font-family:Georgia,serif;font-size:20px;font-weight:bold;vertical-align:middle;margin-left:6px;">Épreuve</span>
        </td></tr>
        <tr><td style="padding:8px 28px 0;">
          <h1 style="font-family:Georgia,serif;font-size:22px;margin:12px 0;">Reset your password</h1>
          <p style="font-size:16px;line-height:1.6;margin:0 0 16px;">Hi {first}, someone (hopefully you) asked to reset the password for your Épreuve account.</p>
          <p style="margin:24px 0;">
            <a href="{safe_link}" style="background:#145c4a;color:#fffdf8;text-decoration:none;font-weight:bold;padding:12px 22px;border-radius:10px;display:inline-block;">Choose a new password</a>
          </p>
          <p style="font-size:14px;line-height:1.6;color:#5f594d;margin:0 0 16px;">This link works once and expires in {minutes} minutes. If the button doesn't work, paste this into your browser:<br><a href="{safe_link}" style="color:#145c4a;word-break:break-all;">{safe_link}</a></p>
          <p style="font-size:14px;line-height:1.6;color:#5f594d;margin:0 0 28px;">If you didn't ask for this, ignore this email. Your password won't change.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return Email(to=to, subject="Reset your Épreuve password", html=body, text=text)
