"""
Gmail MCP Server v3
Priority stack: SMTP → GWS CLI → Google OAuth2

Designed by Vera + Dmitri + Nadia:
- SMTP stays primary (fastest, simplest, already working)
- GWS CLI as middle layer (easy auth via 'gws auth login')
- OAuth2 as legacy fallback (requires manual refresh_token setup)
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import logging
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from config import settings

logger = logging.getLogger(__name__)

# Tool Input Schemas
class SendEmailInput(BaseModel):
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body content (text or HTML)")
    is_html: bool = Field(True, description="Whether body is HTML")
    attachment_path: Optional[str] = Field(None, description="Path to file attachment (e.g. PDF)")

class ReadInboxInput(BaseModel):
    query: str = Field("", description="Gmail search query (e.g., 'is:unread')")
    max_results: int = Field(10, description="Max emails to retrieve")

class CheckScheduleInput(BaseModel):
    date_str: str = Field(..., description="Date to check schedule in YYYY-MM-DD format")


class GmailMCPServer:
    """
    Gmail MCP Server v3 — Three-tier email delivery:
    1. SMTP (primary — fast, App Password auth)
    2. GWS CLI (fallback — simple 'gws auth login')
    3. Google OAuth2 API (legacy — manual refresh_token)
    """
    def __init__(self):
        self.name = "gmail-mcp-server"
        self.version = "3.0.0"  # v3: SMTP → GWS → OAuth2

        self.tools = {
            "send_email": self.send_email,
            "read_inbox": self.read_inbox,
            "check_schedule": self.check_schedule
        }

    def _has_smtp_credentials(self) -> bool:
        return bool(settings.smtp_username and settings.smtp_password)

    def _has_oauth2_credentials(self) -> bool:
        return bool(
            getattr(settings, 'google_refresh_token', '') 
            and settings.google_refresh_token != "your_refresh_token"
        )

    # ══════════════════════════════════════════════════════════════
    # SEND EMAIL — SMTP → GWS → OAuth2
    # ══════════════════════════════════════════════════════════════

    def send_email(self, input_data: SendEmailInput) -> Dict[str, Any]:
        """Send email via 3-tier priority: SMTP → GWS CLI → OAuth2."""
        # Priority 1: SMTP (fastest, most reliable)
        if self._has_smtp_credentials():
            result = self._send_via_smtp(input_data)
            if result["success"]:
                return result
            logger.warning(f"⚠️ SMTP failed, trying GWS CLI...")

        # Priority 2: GWS CLI
        result = self._send_via_gws(input_data)
        if result["success"]:
            return result

        # Priority 3: OAuth2 (legacy)
        if self._has_oauth2_credentials():
            logger.warning("⚠️ GWS CLI failed, trying OAuth2...")
            return self._send_via_oauth2(input_data)

        return {
            "success": False,
            "error": "No email method available. Set SMTP_USERNAME+SMTP_PASSWORD in .env, or run 'gws auth login', or set Google OAuth2 credentials."
        }

    def _send_via_smtp(self, input_data: SendEmailInput) -> Dict[str, Any]:
        """Send email using SMTP with TLS. Supports PDF attachments."""
        try:
            msg = MIMEMultipart()
            msg["From"] = settings.smtp_username
            msg["To"] = input_data.to_email
            msg["Subject"] = input_data.subject

            content_type = "html" if input_data.is_html else "plain"
            msg.attach(MIMEText(input_data.body, content_type))

            # Attachment (PDF)
            if input_data.attachment_path and os.path.exists(input_data.attachment_path):
                with open(input_data.attachment_path, "rb") as f:
                    attachment = MIMEApplication(f.read(), _subtype="pdf")
                    filename = os.path.basename(input_data.attachment_path)
                    attachment.add_header("Content-Disposition", "attachment", filename=filename)
                    msg.attach(attachment)
                logger.info(f"📎 Attached PDF: {input_data.attachment_path}")

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)

            logger.info(f"✅ Email sent via SMTP to {input_data.to_email}")
            return {"success": True, "method": "smtp", "message": f"Email sent to {input_data.to_email}"}

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ SMTP auth failed: {e}")
            return {"success": False, "method": "smtp", "error": f"SMTP auth failed: {e}"}
        except Exception as e:
            logger.error(f"❌ SMTP send failed: {e}")
            return {"success": False, "method": "smtp", "error": str(e)}

    def _send_via_gws(self, input_data: SendEmailInput) -> Dict[str, Any]:
        """Send email via GWS CLI subprocess."""
        try:
            from utils.gws_bridge import gws_send_email, gws_available
            if not gws_available():
                return {"success": False, "method": "gws", "error": "GWS CLI not available"}

            result = gws_send_email(
                to_email=input_data.to_email,
                subject=input_data.subject,
                body=input_data.body,
                is_html=input_data.is_html,
                attachment_path=input_data.attachment_path
            )
            return result

        except Exception as e:
            logger.error(f"❌ GWS email failed: {e}")
            return {"success": False, "method": "gws", "error": str(e)}

    def _send_via_oauth2(self, input_data: SendEmailInput) -> Dict[str, Any]:
        """Legacy: send via Google OAuth2 Gmail API."""
        try:
            import base64
            from email.message import EmailMessage
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = self._get_oauth2_credentials()
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)

            msg = EmailMessage()
            msg.set_content(input_data.body, subtype="html" if input_data.is_html else "plain")
            msg["To"] = input_data.to_email
            msg["From"] = settings.admin_email
            msg["Subject"] = input_data.subject

            encoded_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            send_message = service.users().messages().send(
                userId="me", body={"raw": encoded_message}
            ).execute()

            return {
                "success": True,
                "method": "oauth2",
                "message_id": send_message["id"],
                "message": f"Email sent to {input_data.to_email}"
            }
        except Exception as e:
            logger.error(f"❌ OAuth2 email failed: {e}")
            return {"success": False, "method": "oauth2", "error": str(e)}

    # ══════════════════════════════════════════════════════════════
    # READ INBOX — GWS → OAuth2
    # ══════════════════════════════════════════════════════════════

    def read_inbox(self, input_data: ReadInboxInput) -> Dict[str, Any]:
        """Read inbox via GWS CLI (primary) or OAuth2 (fallback)."""
        # Priority 1: GWS CLI
        result = self._read_inbox_via_gws(input_data)
        if result["success"]:
            return result

        # Priority 2: OAuth2
        if self._has_oauth2_credentials():
            return self._read_inbox_via_oauth2(input_data)

        return {"success": False, "error": "No inbox method available. Run 'gws auth login' or set OAuth2 credentials."}

    def _read_inbox_via_gws(self, input_data: ReadInboxInput) -> Dict[str, Any]:
        """Read inbox via GWS CLI."""
        try:
            from utils.gws_bridge import gws_read_inbox, gws_available
            if not gws_available():
                return {"success": False, "error": "GWS CLI not available"}
            return gws_read_inbox(query=input_data.query, max_results=input_data.max_results)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _read_inbox_via_oauth2(self, input_data: ReadInboxInput) -> Dict[str, Any]:
        """Read inbox via OAuth2 Gmail API."""
        try:
            from googleapiclient.discovery import build
            creds = self._get_oauth2_credentials()
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)

            results = service.users().messages().list(
                userId="me", q=input_data.query, maxResults=input_data.max_results
            ).execute()

            messages = results.get("messages", [])
            parsed_messages = []

            for msg in messages:
                msg_data = service.users().messages().get(
                    userId="me", id=msg["id"], format="metadata",
                    metadataHeaders=["Subject", "From", "Date"]
                ).execute()

                headers = msg_data.get("payload", {}).get("headers", [])
                meta = {h["name"]: h["value"] for h in headers}

                parsed_messages.append({
                    "id": msg["id"],
                    "snippet": msg_data.get("snippet", ""),
                    "subject": meta.get("Subject", "No Subject"),
                    "from": meta.get("From", "Unknown"),
                    "date": meta.get("Date", "")
                })

            return {"success": True, "messages": parsed_messages, "count": len(parsed_messages)}
        except Exception as e:
            logger.error(f"❌ OAuth2 inbox read failed: {e}")
            return {"success": False, "error": str(e)}

    # ══════════════════════════════════════════════════════════════
    # CHECK SCHEDULE — GWS → OAuth2
    # ══════════════════════════════════════════════════════════════

    def check_schedule(self, input_data: CheckScheduleInput) -> Dict[str, Any]:
        """Check calendar schedule via GWS CLI (primary) or OAuth2 (fallback)."""
        # Priority 1: GWS CLI
        result = self._check_schedule_via_gws(input_data)
        if result["success"]:
            return result

        # Priority 2: OAuth2
        if self._has_oauth2_credentials():
            return self._check_schedule_via_oauth2(input_data)

        return {"success": False, "error": "No calendar method available. Run 'gws auth login' or set OAuth2 credentials."}

    def _check_schedule_via_gws(self, input_data: CheckScheduleInput) -> Dict[str, Any]:
        """Check schedule via GWS CLI."""
        try:
            from utils.gws_bridge import gws_list_events, gws_available
            if not gws_available():
                return {"success": False, "error": "GWS CLI not available"}

            result = gws_list_events(date_str=input_data.date_str)
            if result["success"]:
                events = result.get("data", {}).get("items", [])
                schedule = []
                for event in events:
                    start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
                    end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date", ""))
                    schedule.append({
                        "summary": event.get("summary", "Busy"),
                        "start": start,
                        "end": end
                    })
                return {"success": True, "date": input_data.date_str, "events": schedule, "count": len(schedule)}
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _check_schedule_via_oauth2(self, input_data: CheckScheduleInput) -> Dict[str, Any]:
        """Check schedule via OAuth2 Calendar API."""
        try:
            from googleapiclient.discovery import build
            creds = self._get_oauth2_credentials()
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)

            time_min = f"{input_data.date_str}T00:00:00Z"
            time_max = f"{input_data.date_str}T23:59:59Z"

            events_result = service.events().list(
                calendarId='primary', timeMin=time_min, timeMax=time_max,
                maxResults=20, singleEvents=True, orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            schedule = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                schedule.append({"summary": event.get("summary", "Busy"), "start": start, "end": end})

            return {"success": True, "date": input_data.date_str, "events": schedule, "count": len(schedule)}
        except Exception as e:
            logger.error(f"❌ OAuth2 schedule check failed: {e}")
            return {"success": False, "error": str(e)}

    # ══════════════════════════════════════════════════════════════
    # SHARED HELPERS
    # ══════════════════════════════════════════════════════════════

    def _get_oauth2_credentials(self):
        """Build Google OAuth2 credentials from config."""
        from google.oauth2.credentials import Credentials
        return Credentials(
            token=None,
            refresh_token=settings.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )


# Singleton instance
gmail_mcp = GmailMCPServer()
