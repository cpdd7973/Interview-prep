"""
Calendar MCP Server
Handles creating and managing Google Calendar events.
"""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import logging
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

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
    Calendar MCP Server for managing interview schedules.
    """
    def __init__(self):
        self.name = "calendar-mcp-server"
        self.version = "1.0.0"
        
        self.tools = {
            "create_event": self.create_event,
            "find_free_slots": self.find_free_slots,
            "cancel_event": self.cancel_event,
            "reschedule_event": self.reschedule_event
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

    def _get_calendar_service(self):
        creds = self._get_credentials()
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def create_event(self, input_data: CreateEventInput) -> Dict[str, Any]:
        try:
            service = self._get_calendar_service()
            
            event = {
                'summary': input_data.summary,
                'description': input_data.description,
                'start': {
                    'dateTime': input_data.start_time.isoformat() + 'Z',
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': input_data.end_time.isoformat() + 'Z',
                    'timeZone': 'UTC',
                },
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
                "event_id": created_event.get('id'),
                "event_link": created_event.get('htmlLink'),
                "message": "Event created and invitations sent"
            }
        except Exception as e:
            logger.error(f"❌ Error creating calendar event: {e}")
            return {"success": False, "error": str(e)}

    def find_free_slots(self, input_data: FindFreeSlotsInput) -> Dict[str, Any]:
        """Find free time slots on a given date using FreeBusy API"""
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
            
            # Simple assumption: working hours 09:00 to 17:00 UTC
            # Return raw busy slots to agents so they can infer
            return {
                "success": True,
                "date": input_data.date_str,
                "busyslots": busy_slots,
                "duration_needed": input_data.duration_minutes
            }
        except Exception as e:
            logger.error(f"❌ Error finding free slots: {e}")
            return {"success": False, "error": str(e)}

    def cancel_event(self, input_data: CancelEventInput) -> Dict[str, Any]:
        try:
            service = self._get_calendar_service()
            
            service.events().delete(
                calendarId='primary', eventId=input_data.event_id, sendUpdates='all'
            ).execute()
            
            return {
                "success": True,
                "event_id": input_data.event_id,
                "message": "Event cancelled successfully"
            }
        except Exception as e:
            logger.error(f"❌ Error cancelling event: {e}")
            return {"success": False, "error": str(e)}

    def reschedule_event(self, input_data: RescheduleEventInput) -> Dict[str, Any]:
        try:
            service = self._get_calendar_service()
            
            event = service.events().get(calendarId='primary', eventId=input_data.event_id).execute()
            
            event['start']['dateTime'] = input_data.new_start_time.isoformat() + 'Z'
            event['end']['dateTime'] = input_data.new_end_time.isoformat() + 'Z'
            
            updated_event = service.events().update(
                calendarId='primary', eventId=input_data.event_id, body=event, sendUpdates='all'
            ).execute()
            
            return {
                "success": True,
                "event_id": updated_event['id'],
                "message": "Event rescheduled successfully"
            }
        except Exception as e:
            logger.error(f"❌ Error rescheduling event: {e}")
            return {"success": False, "error": str(e)}

# Singleton instance
calendar_mcp = CalendarMCPServer()
