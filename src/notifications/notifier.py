"""Multi-channel notifier — Telegram and/or email.

Channels are activated only when their env vars are set.
If neither is configured, messages are only logged (no crash).

Telegram setup:
  1. Message @BotFather → /newbot → get TELEGRAM_TOKEN
  2. Message your bot, then visit:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     to find your TELEGRAM_CHAT_ID

Email setup (Gmail example):
  - Enable "App Passwords" in Google account security
  - Use the 16-char app password as SMTP_PASSWORD
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Emojis for message levels
_ICONS = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "🚨", "TRADE": "💹"}


class Notifier:
    """Send notifications to Telegram and/or email.

    All parameters are optional — unconfigured channels are silently skipped.
    """

    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        email_to: Optional[str] = None,
        email_from: Optional[str] = None,
    ) -> None:
        self._tg_token = telegram_token
        self._tg_chat_id = telegram_chat_id
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._email_to = email_to
        self._email_from = email_from or smtp_user

        channels = []
        if self._tg_token and self._tg_chat_id:
            channels.append("Telegram")
        if self._smtp_host and self._email_to:
            channels.append("Email")
        logger.info(
            "Notifier ready — active channels: %s",
            ", ".join(channels) if channels else "none (notifications disabled)",
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def send(self, subject: str, body: str = "", level: str = "INFO") -> None:
        """Send notification on all configured channels.

        Args:
            subject: Short one-line summary (used as email subject / Telegram title).
            body:    Optional detail text.
            level:   INFO | WARNING | ERROR | TRADE
        """
        icon = _ICONS.get(level, "")
        full_message = f"{icon} {subject}"
        if body:
            full_message += f"\n\n{body}"

        self._send_telegram(full_message)
        self._send_email(subject=f"{icon} {subject}", body=full_message)

    def send_error(self, subject: str, body: str = "") -> None:
        self.send(subject, body, level="ERROR")

    def send_trade(self, subject: str, body: str = "") -> None:
        self.send(subject, body, level="TRADE")

    def send_warning(self, subject: str, body: str = "") -> None:
        self.send(subject, body, level="WARNING")

    # ── Telegram ───────────────────────────────────────────────────────────

    def _send_telegram(self, text: str) -> None:
        if not (self._tg_token and self._tg_chat_id):
            return
        url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": self._tg_chat_id, "text": text},
                timeout=10,
            )
            resp.raise_for_status()
            logger.debug("Telegram notification sent")
        except Exception as exc:
            logger.error("Telegram notification failed: %s", exc)

    # ── Email ──────────────────────────────────────────────────────────────

    def _send_email(self, subject: str, body: str) -> None:
        if not (self._smtp_host and self._email_to):
            return
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self._email_from or ""
        msg["To"] = self._email_to
        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=10) as s:
                s.starttls()
                if self._smtp_user and self._smtp_password:
                    s.login(self._smtp_user, self._smtp_password)
                s.send_message(msg)
            logger.debug("Email notification sent to %s", self._email_to)
        except Exception as exc:
            logger.error("Email notification failed: %s", exc)
