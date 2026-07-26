"""
email_actions.py
----------------
Open Gmail compose with a pre-filled recipient, subject, and body.
ALWAYS requires confirmation before the user clicks Send — this module
never auto-sends.

Public API:
    compose_email(recipient, subject, body, confirm_fn) -> dict
"""

from __future__ import annotations

import logging
import urllib.parse
import webbrowser
from typing import Callable, Optional

logger = logging.getLogger("jarvis.email")

# Address book — display name -> email. Extend at runtime via
# add_recipient. The planner passes a free-form "recipient" string from
# the user; we try to resolve it to an address below.
_RECIPIENTS: dict[str, str] = {
    "harshith":     "harshith@example.com",
    "bhajan":       "bhajan@example.com",
    "professor":    "professor@example.edu",
    "placement":    "placement.officer@example.edu",
    "placement officer": "placement.officer@example.edu",
    "mom":          "mom@example.com",
    "dad":          "dad@example.com",
}


def add_recipient(name: str, email: str) -> None:
    _RECIPIENTS[name.strip().lower()] = email.strip()


def resolve_recipient(name: str) -> tuple[str, bool]:
    key = (name or "").strip().lower()
    if key in _RECIPIENTS:
        return _RECIPIENTS[key], True
    for k, v in _RECIPIENTS.items():
        if k in key or key in k:
            return v, False
    return "", False


def _default_confirm(prompt: str) -> bool:
    try:
        ans = input(f"\n{prompt} [y/N]: ").strip().lower()
        return ans in ("y", "yes")
    except EOFError:
        return False


def compose_email(
    recipient: str,
    subject: str,
    body: str = "",
    confirm_fn: Optional[Callable[[str], bool]] = None,
    auto_open: bool = True,
) -> dict:
    """Open Gmail compose with pre-filled fields. Asks for confirmation
    before proceeding."""
    if not recipient:
        return {"ok": False, "error": "Recipient is required, sir."}

    address, exact = resolve_recipient(recipient)
    # If we don't have a stored address but the recipient string already
    # looks like an email, use it directly.
    if not address and "@" in recipient:
        address = recipient.strip()
        exact = True

    confirm = confirm_fn or _default_confirm
    if not confirm(
        f"Compose email to {recipient or address} — subject '{subject}'?"
    ):
        return {"ok": False, "cancelled": True, "message": "Cancelled, sir."}

    params = {
        "view": "cm",
        "fs": "1",
        "to": address or recipient,
        "su": subject or "",
        "body": body or "",
    }
    url = "https://mail.google.com/mail/?" + urllib.parse.urlencode(params)

    opened = False
    if auto_open:
        try:
            opened = webbrowser.open(url, new=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to open browser: %s", exc)

    if not exact and address:
        note = (
            f" I guessed the address for {recipient}; please verify it "
            f"before sending."
        )
    elif not address:
        note = f" I could not find a stored address for {recipient}."
    else:
        note = ""

    return {
        "ok": True,
        "url": url,
        "opened": opened,
        "to": address or recipient,
        "subject": subject,
        "body": body,
        "tts": f"Email drafted, sir.{note} Please review and click Send in Gmail.",
    }
