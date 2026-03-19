"""
Calendar MCP Server v2
Priority stack: GWS CLI → Google OAuth2

Designed by Vera + Dmitri:
- GWS CLI as primary (one-time 'gws auth login', no refresh_token needed)
- OAuth2 as legacy fallback (requires manual credential setup)
"""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import logging
from datetime import datetime, timedelta

from config import settings

logger = logging.getLogger(__name__)

# Tool Input Schemas
class CreateEventInput(BaseModel):
    summary: str = Field(..., description="Event title")
    start_time: datetime = Field(..., description="Start time (UTC)")
    end_time: datetime = Field(..., description="End time (UTC)")
    attendees: List[str] = Field(..., description="List of attendee emails")
    description: Optional[str] = Field(None, description="Event description")

class FindFreeSlotsInput(BaseModel):
    date_str: str = Field(..., description="Date to check in YYYY-MM-DD format")
    duration_minutes: int = Field(60, description="Duration needed in minutes")

class CancelEventInput(BaseModel):
    event_id: str = Field(..., description="Google Calendar event ID")

class RescheduleEventInput(BaseModel):
    event_id: str = Field(..., description="Google Calendar event ID")
    new_start_time: datetime = Field(..., description="New start time (UTC)")
    new_end_time: datetime = Field(..., description="New end time (UTC)")


class CalendarMCPServer:
    """
    Calendar MCP Server v2 — Two-tier calendar management:
    1. GWS CLI (primary — simple 'gws auth login')
    2. Google OAuth2 API (fallback — manual refresh_token)
    """
    def __init__(self):
        self.name = "calendar-mcp-server"
        self.version = "2.0.0"  # v2: GWS primary + OAuth2 fallback

        self.tools = {
            "create_event": self.create_event,
            "find_free_slots": self.find_free_slots,
            "cancel_event": self.cancel_event,
            "reschedule_event": self.reschedule_event
        }

    def _has_oauth2_credentials(self) -> bool:
        return bool(
            getattr(settings, 'google_refresh_token', '')
            and settings.google_refresh_token != "your_refresh_token"
        )

    # ══════════════════════════════════════════════════════════════
    # CREATE EVENT — GWS → OAuth2
    # ══════════════════════════════════════════════════════════════

    def create_event(self, input_data: CreateEventInput) -> Dict[str, Any]:
        """Create calendar event via GWS CLI (primary) or OAuth2 (fallback)."""
        # Priority 1: GWS CLI
        result = self._create_event_gws(input_data)
        if result["success"]:
            return result

        # Priority 2: OAuth2
        if self._has_oauth2_credentials():
            logger.info("⚠️ GWS failed, trying OAuth2 for calendar event...")
            return self._create_event_oauth2(input_data)
        
        return {"success": False, "error": "No calendar method available. Run 'gws auth login' or set OAuth2 credentials."}

    def _create_event_gws(self, input_data: CreateEventInput) -> Dict[str, Any]:
        """Create event via GWS CLI."""
        try:
            from utils.gws_bridge import gws_create_event, gws_available
            if not gws_available():
                return {"success": False, "error": "GWS CLI not available"}

            result = gws_create_event(
                summary=input_data.summary,
                start_time=input_data.start_time.isoformat() + "Z",
                end_time=input_data.end_time.isoformat() + "Z",
                attendees=input_data.attendees,
                description=input_data.description
            )

            if result["success"]:
                return {
                    "success": True,
                    "method": "gws",
                    "event_id": result.get("event_id", ""),
                    "event_link": result.get("event_link", ""),
                    "message": "Event created via GWS CLI"
                }
            return result
        except Exception as e:
            logger.error(f"❌ GWS calendar create failed: {e}")
            return {"success": False, "error": str(e)}

    def _create_event_oauth2(self, input_data: CreateEventInput) -> Dict[str, Any]:
        """Create event via OAuth2 Calendar API."""
        try:
            service = self._get_calendar_service()

            event = {
                'summary': input_data.summary,
                'description': input_data.description,
                'start': {'dateTime': input_data.start_time.isoformat() + 'Z', 'timeZone': 'UTC'},
                'end': {'dateTime': input_data.end_time.isoformat() + 'Z', 'timeZone': 'UTC'},
                'attendees': [{'email': email} for email in input_data.attendees],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},
                        {'method': 'popup', 'minutes': 10},
                    ],
                },
            }

            created_event = service.events().insert(
                calendarId='primary', body=event, sendUpdates='all'
            ).execute()

            return {
                "success": True,
                "method": "oauth2",
                "event_id": created_event.get('id'),
                "event_link": created_event.get('htmlLink'),
                "message": "Event created via OAuth2"
            }
        except Exception as e:
            logger.error(f"❌ OAuth2 calendar create failed: {e}")
            return {"success": False, "error": str(e)}

    # ══════════════════════════════════════════════════════════════
    # FIND FREE SLOTS — GWS → OAuth2
    # ══════════════════════════════════════════════════════════════

    def find_free_slots(self, input_data: FindFreeSlotsInput) -> Dict[str, Any]:
        """Find free time slots via GWS CLI (primary) or OAuth2 (fallback)."""
        # Priority 1: GWS CLI
        result = self._find_free_slots_gws(input_data)
        if result["success"]:
            return result

        # Priority 2: OAuth2
        if self._has_oauth2_credentials():
            return self._find_free_slots_oauth2(input_data)

        return {"success": False, "error": "No calendar method available."}

    def _find_free_slots_gws(self, input_data: FindFreeSlotsInput) -> Dict[str, Any]:
        """Find busy slots via GWS CLI events list."""
        try:
            from utils.gws_bridge import gws_list_events, gws_available
            if not gws_available():
                return {"success": False, "error": "GWS CLI not available"}

            result = gws_list_events(date_str=input_data.date_str)
            if result["success"]:
                events = result.get("data", {}).get("items", [])
                busy_slots = []
                for event in events:
                    start = event.get("start", {}).get("dateTime", "")
                    end = event.get("end", {}).get("dateTime", "")
                    if start and end:
                        busy_slots.append({"start": start, "end": end})
                return {
                    "success": True,
                    "method": "gws",
                    "date": input_data.date_str,
                    "busyslots": busy_slots,
                    "duration_needed": input_data.duration_minutes
                }
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _find_free_slots_oauth2(self, input_data: FindFreeSlotsInput) -> Dict[str, Any]:
        """Find free slots via OAuth2 FreeBusy API."""
        try:
            service = self._get_calendar_service()

            time_min = f"{input_data.date_str}T00:00:00Z"
            time_max = f"{input_data.date_str}T23:59:59Z"

            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "timeZone": "UTC",
                "items": [{"id": 'primary'}]
            }

            freebusy_req = service.freebusy().query(body=body).execute()
            busy_slots = freebusy_req['calendars']['primary']['busy']

            return {
                "success": True,
                "method": "oauth2",
                "date": input_data.date_str,
                "busyslots": busy_slots,
                "duration_needed": input_data.duration_minutes
            }
        except Exception as e:
            logger.error(f"❌ OAuth2 freebusy failed: {e}")
            return {"success": False, "error": str(e)}

    # ══════════════════════════════════════════════════════════════
    # CANCEL EVENT — GWS → OAuth2
    # ══════════════════════════════════════════════════════════════

    def cancel_event(self, input_data: CancelEventInput) -> Dict[str, Any]:
        """Cancel event via GWS CLI (primary) or OAuth2 (fallback)."""
        result = self._cancel_event_gws(input_data)
        if result["success"]:
            return result

        if self._has_oauth2_credentials():
            return self._cancel_event_oauth2(input_data)

        return {"success": False, "error": "No calendar method available."}

    def _cancel_event_gws(self, input_data: CancelEventInput) -> Dict[str, Any]:
        try:
            from utils.gws_bridge import gws_cancel_event, gws_available
            if not gws_available():
                return {"success": False, "error": "GWS CLI not available"}
            result = gws_cancel_event(event_id=input_data.event_id)
            if result["success"]:
                return {"success": True, "method": "gws", "event_id": input_data.event_id, "message": "Event cancelled via GWS"}
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _cancel_event_oauth2(self, input_data: CancelEventInput) -> Dict[str, Any]:
        try:
            service = self._get_calendar_service()
            service.events().delete(
                calendarId='primary', eventId=input_data.event_id, sendUpdates='all'
            ).execute()
            return {"success": True, "method": "oauth2", "event_id": input_data.event_id, "message": "Event cancelled via OAuth2"}
        except Exception as e:
            logger.error(f"❌ OAuth2 cancel failed: {e}")
            return {"success": False, "error": str(e)}

    # ══════════════════════════════════════════════════════════════
    # RESCHEDULE EVENT — GWS → OAuth2
    # ══════════════════════════════════════════════════════════════

    def reschedule_event(self, input_data: RescheduleEventInput) -> Dict[str, Any]:
        """Reschedule event via GWS CLI (primary) or OAuth2 (fallback)."""
        result = self._reschedule_event_gws(input_data)
        if result["success"]:
            return result

        if self._has_oauth2_credentials():
            return self._reschedule_event_oauth2(input_data)

        return {"success": False, "error": "No calendar method available."}

    def _reschedule_event_gws(self, input_data: RescheduleEventInput) -> Dict[str, Any]:
        try:
            from utils.gws_bridge import gws_reschedule_event, gws_available
            if not gws_available():
                return {"success": False, "error": "GWS CLI not available"}
            result = gws_reschedule_event(
                event_id=input_data.event_id,
                new_start_time=input_data.new_start_time.isoformat() + "Z",
                new_end_time=input_data.new_end_time.isoformat() + "Z"
            )
            if result["success"]:
                return {"success": True, "method": "gws", "event_id": input_data.event_id, "message": "Event rescheduled via GWS"}
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _reschedule_event_oauth2(self, input_data: RescheduleEventInput) -> Dict[str, Any]:
        try:
            service = self._get_calendar_service()
            event = service.events().get(calendarId='primary', eventId=input_data.event_id).execute()
            event['start']['dateTime'] = input_data.new_start_time.isoformat() + 'Z'
            event['end']['dateTime'] = input_data.new_end_time.isoformat() + 'Z'

            updated_event = service.events().update(
                calendarId='primary', eventId=input_data.event_id, body=event, sendUpdates='all'
            ).execute()

            return {"success": True, "method": "oauth2", "event_id": updated_event['id'], "message": "Event rescheduled via OAuth2"}
        except Exception as e:
            logger.error(f"❌ OAuth2 reschedule failed: {e}")
            return {"success": False, "error": str(e)}

    # ══════════════════════════════════════════════════════════════
    # SHARED HELPERS
    # ══════════════════════════════════════════════════════════════

    def _get_calendar_service(self):
        """Build Google Calendar service via OAuth2."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials(
            token=None,
            refresh_token=settings.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)


# Singleton instance
calendar_mcp = CalendarMCPServer()
