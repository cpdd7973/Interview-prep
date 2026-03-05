"""
Gmail MCP Server
Handles sending and reading emails via Google Workspace/Gmail API.
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import logging
import base64
from email.message import EmailMessage
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import settings

logger = logging.getLogger(__name__)

# Tool Input Schemas
class SendEmailInput(BaseModel):
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body content (text or HTML)")
    is_html: bool = Field(True, description="Whether body is HTML")

class ReadInboxInput(BaseModel):
    query: str = Field("", description="Gmail search query (e.g., 'is:unread')")
    max_results: int = Field(10, description="Max emails to retrieve")

class CheckScheduleInput(BaseModel):
    date_str: str = Field(..., description="Date to check schedule in YYYY-MM-DD format")

class GmailMCPServer:
    """
    Gmail MCP Server for sending and receiving emails.
    """
    def __init__(self):
        self.name = "gmail-mcp-server"
        self.version = "1.0.0"
        
        self.tools = {
            "send_email": self.send_email,
            "read_inbox": self.read_inbox,
            "check_schedule": self.check_schedule
        }

    def _get_credentials(self) -> Credentials:
        """Build Google OAuth2 credentials from config refresh token"""
        return Credentials(
            token=None,
            refresh_token=settings.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )

    def _get_gmail_service(self):
        creds = self._get_credentials()
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def send_email(self, input_data: SendEmailInput) -> Dict[str, Any]:
        try:
            service = self._get_gmail_service()
            
            msg = EmailMessage()
            msg.set_content(input_data.body, subtype="html" if input_data.is_html else "plain")
            msg["To"] = input_data.to_email
            msg["From"] = settings.admin_email
            msg["Subject"] = input_data.subject
            
            encoded_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            create_message = {"raw": encoded_message}
            
            send_message = service.users().messages().send(
                userId="me", body=create_message
            ).execute()
            
            return {
                "success": True,
                "message_id": send_message["id"],
                "message": f"Email sent to {input_data.to_email}"
            }
        except Exception as e:
            logger.error(f"❌ Error sending email: {e}")
            return {"success": False, "error": str(e)}

    def read_inbox(self, input_data: ReadInboxInput) -> Dict[str, Any]:
        try:
            service = self._get_gmail_service()
            
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
                
            return {
                "success": True,
                "messages": parsed_messages,
                "count": len(parsed_messages)
            }
        except Exception as e:
            logger.error(f"❌ Error reading inbox: {e}")
            return {"success": False, "error": str(e)}

    def check_schedule(self, input_data: CheckScheduleInput) -> Dict[str, Any]:
        """
        Check admin calendar for specific day using Calendar API.
        Included here per build sequence, but actually calls Calendar API.
        """
        try:
            creds = self._get_credentials()
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            
            # Start and end of the day requested
            time_min = f"{input_data.date_str}T00:00:00Z"
            time_max = f"{input_data.date_str}T23:59:59Z"
            
            events_result = service.events().list(
                calendarId='primary', timeMin=time_min, timeMax=time_max,
                maxResults=20, singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            schedule = []
            
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                schedule.append({
                    "summary": event.get("summary", "Busy"),
                    "start": start,
                    "end": end
                })
                
            return {
                "success": True,
                "date": input_data.date_str,
                "events": schedule,
                "count": len(schedule)
            }
        except Exception as e:
            logger.error(f"❌ Error checking schedule: {e}")
            return {"success": False, "error": str(e)}

# Singleton instance
gmail_mcp = GmailMCPServer()
