"""Sending email through Gmail (or any SMTP server).

Settings come from environment variables (Vercel -> Settings -> Environment
Variables, or .env locally):

    SMTP_USER       the Gmail address that sends, e.g. knyc.candelaria@gmail.com
    SMTP_PASSWORD   a Gmail *app password* (16 letters), not the normal password
    MAIL_FROM_NAME  optional display name (default: the organization's name)
    MAIL_REPLY_TO   optional address that replies go to
    SMTP_HOST       optional, default smtp.gmail.com
    SMTP_PORT       optional, default 587 (STARTTLS)

Gmail's free limit is about 500 recipients a day.
"""

import html
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

ORG_NAME = "Kaya Natin! Youth – Candelaria"


class MailError(Exception):
    """A problem that is safe to show to an admin (never contains secrets)."""


@dataclass(frozen=True)
class MailConfig:
    host: str
    port: int
    user: str
    password: str
    from_name: str
    reply_to: str


def config():
    try:
        port = int((os.getenv("SMTP_PORT") or "587").strip())
    except ValueError:
        port = 587
    return MailConfig(
        host=(os.getenv("SMTP_HOST") or "smtp.gmail.com").strip(),
        port=port,
        user=(os.getenv("SMTP_USER") or "").strip(),
        # Google shows app passwords in groups of four ("abcd efgh ...").
        password=(os.getenv("SMTP_PASSWORD") or "").replace(" ", "").strip(),
        from_name=(os.getenv("MAIL_FROM_NAME") or ORG_NAME).strip(),
        reply_to=(os.getenv("MAIL_REPLY_TO") or "").strip(),
    )


def is_configured():
    cfg = config()
    return bool(cfg.user and cfg.password)


def sender_address():
    return config().user


def _html_body(text):
    paragraphs = "".join(
        "<p style=\"margin:0 0 14px\">"
        + html.escape(block).replace("\n", "<br>")
        + "</p>"
        for block in text.strip().split("\n\n")
    )
    return (
        "<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:15px;"
        "line-height:1.5;color:#222;max-width:600px\">"
        f"{paragraphs}"
        "<hr style=\"border:none;border-top:1px solid #ddd;margin:24px 0 12px\">"
        "<p style=\"font-size:12px;color:#777;margin:0\">"
        f"Sent by {html.escape(ORG_NAME)}. You are receiving this because you are "
        "listed as a member of the organization.</p></div>"
    )


def build_message(cfg, to_email, subject, text):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg.from_name, cfg.user))
    msg["To"] = to_email
    if cfg.reply_to:
        msg["Reply-To"] = cfg.reply_to
    msg["Message-ID"] = make_msgid(domain=cfg.user.split("@")[-1] or None)
    footer = (
        f"\n\n--\nSent by {ORG_NAME}. You are receiving this because you are "
        "listed as a member of the organization."
    )
    msg.set_content(text.strip() + footer)
    msg.add_alternative(_html_body(text), subtype="html")
    return msg


class Mailer:
    """One SMTP connection reused for a whole batch.

        with Mailer() as mailer:
            mailer.send("a@example.com", "Subject", "Body")
    """

    def __init__(self, timeout=15):
        self.cfg = config()
        self.timeout = timeout
        self._smtp = None

    def __enter__(self):
        if not (self.cfg.user and self.cfg.password):
            raise MailError(
                "Email is not set up yet. Add SMTP_USER and SMTP_PASSWORD "
                "(a Gmail app password) in Vercel, then redeploy."
            )
        self._connect()
        return self

    def __exit__(self, *exc):
        if self._smtp is not None:
            try:
                self._smtp.quit()
            except (smtplib.SMTPException, OSError):
                pass
            self._smtp = None
        return False

    def _connect(self):
        try:
            smtp = smtplib.SMTP(self.cfg.host, self.cfg.port, timeout=self.timeout)
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(self.cfg.user, self.cfg.password)
        except smtplib.SMTPAuthenticationError:
            raise MailError(
                "Gmail refused the login. Check SMTP_USER and that SMTP_PASSWORD "
                "is an app password (Google Account -> Security -> App passwords)."
            ) from None
        except (smtplib.SMTPException, OSError):
            raise MailError(
                "Could not connect to the email server. Please try again in a few minutes."
            ) from None
        self._smtp = smtp

    def send(self, to_email, subject, text):
        msg = build_message(self.cfg, to_email, subject, text)
        try:
            self._smtp.send_message(msg)
        except smtplib.SMTPServerDisconnected:
            # Long batches can outlive the connection; reconnect once.
            self._connect()
            self._smtp.send_message(msg)
        except smtplib.SMTPRecipientsRefused:
            raise MailError("The email server refused this address.") from None
        except smtplib.SMTPDataError as error:
            if error.smtp_code in (421, 450, 451, 452, 550) and b"limit" in (error.smtp_error or b"").lower():
                raise MailError("Gmail's daily sending limit was reached. Try again tomorrow.") from None
            raise MailError("The email server rejected the message.") from None
        except (smtplib.SMTPException, OSError):
            raise MailError("Sending failed because of a network problem.") from None
