"""
whatsapp_actions.py
-------------------
Open WhatsApp Web with a pre-filled message. ALWAYS requires confirmation
before the user clicks Send — this module never auto-sends.

Public API:
    send_whatsapp_message(contact, message, confirm_fn) -> dict

Behavior:
    1. Resolves "contact" to a phone number using a small in-memory contact
       book (extendable by the user) and falling back to the contact name.
    2. Builds https://web.whatsapp.com/send?phone=<e164>&text=<urlencoded>
    3. Opens it in the default browser.
    4. Asks the user to confirm before clicking Send.
"""

from __future__ import annotations

import logging
import urllib.parse
import webbrowser
from typing import Callable, Optional

logger = logging.getLogger("jarvis.whatsapp")

# ---------------------------------------------------------------------------
# Contact book. Keys are lowercased. Numbers MUST be in E.164-ish form
# (country code, no leading +, no spaces). Extend as you grow the address
# book. This is the single source of truth that the planner refers to.
# ---------------------------------------------------------------------------
_CONTACTS: dict[str, str] = {
    "maa":      "919346569081",
    "mother":   "919346569081",
    "dad":      "919346939755",
    "father":   "919346939755",
    "brother":  "919989174968",
}


def add_contact(name: str, phone_e164: str) -> None:
    """Register a contact for future WhatsApp actions."""
    cleaned = "".join(ch for ch in phone_e164 if ch.isdigit() or ch == "+")
    cleaned = cleaned.lstrip("+")
    _CONTACTS[name.strip().lower()] = cleaned


def resolve_contact(contact: str) -> tuple[str, bool]:
    """Return (phone_digits, exact_match). Falls back to the literal name
    string if unknown, so WhatsApp Web can still attempt a partial search."""
    key = (contact or "").strip().lower()
    if key in _CONTACTS:
        return _CONTACTS[key], True
    # try a partial match
    for k, v in _CONTACTS.items():
        if k in key or key in k:
            return v, False
    return "", False


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------
def _default_confirm(prompt: str) -> bool:
    """Default confirmation: ask via input(). The orchestration layer in
    jarvis_v2.py can override this with a voice-friendly version."""
    try:
        ans = input(f"\n{prompt} [y/N]: ").strip().lower()
        return ans in ("y", "yes")
    except EOFError:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def send_whatsapp_message(
    contact: str,
    message: str,
    confirm_fn: Optional[Callable[[str], bool]] = None,
    auto_open: bool = True,
) -> dict:
    """Draft a WhatsApp Web message. Opens the pre-filled compose window
    in the default browser and asks the user to confirm before sending."""
    if not contact or not message:
        return {"ok": False, "error": "Contact and message are required, sir."}

    phone, exact = resolve_contact(contact)
    confirm = confirm_fn or _default_confirm

    if phone and exact:
        url = (
            "https://web.whatsapp.com/send?phone="
            + urllib.parse.quote(phone)
            + "&text=" + urllib.parse.quote(message)
            + "&type=phone_number&app_absent=0"
        )
        opened = False
        if auto_open:
            try:
                opened = webbrowser.open(url, new=2)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to open browser: %s", exc)
        msg = (
            f"Message drafted for {contact}, sir. "
            f"Please review and click Send in WhatsApp Web."
        )
        if not confirm(f"Send '{message}' to {contact} ({phone})?"):
            return {"ok": False, "cancelled": True, "message": "Cancelled, sir."}
        return {
            "ok": True,
            "url": url,
            "opened": opened,
            "phone": phone,
            "contact": contact,
            "message": message,
            "tts": msg,
        }

    # No phone number — open chat search by name so user can pick the contact
    url = (
        "https://web.whatsapp.com/send?text="
        + urllib.parse.quote(message)
    )
    if auto_open:
        try:
            webbrowser.open(url, new=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to open browser: %s", exc)
    return {
        "ok": True,
        "url": url,
        "opened": True,
        "contact": contact,
        "message": message,
        "tts": (
            f"I do not have a phone number for {contact}, sir. "
            f"I have opened WhatsApp Web with the message pre-filled. "
            f"Please select the contact and click Send."
        ),
    }
