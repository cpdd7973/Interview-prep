"""
Room MCP Server
Manages Jitsi Meet WebRTC interview rooms (Open Source Alternative).
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import logging
import time

logger = logging.getLogger(__name__)

# Tool Input Schemas (Pydantic models)
class CreateRoomInput(BaseModel):
    room_id: str = Field(..., description="Unique room ID (session ID) to create")
    duration_minutes: int = Field(60, description="How long the room should remain active")

class GetRoomStatusInput(BaseModel):
    room_id: str = Field(..., description="Unique room ID to check")

class DeleteRoomInput(BaseModel):
    room_id: str = Field(..., description="Unique room ID to delete")

class RoomMCPServer:
    """
    Room MCP Server managing Jitsi Meet video/audio WebRTC rooms.
    Jitsi Meet uses URL-based ephemeral rooms, so no API keys or backend state are required.
    """
    def __init__(self):
        self.name = "room-mcp-server"
        self.version = "1.0.0"
        self.base_url = "https://meet.ffmuc.net"
        
        self.tools = {
            "create_daily_room": self.create_daily_room,
            "get_room_status": self.get_room_status,
            "delete_room": self.delete_room,
            "list_active_rooms": self.list_active_rooms
        }

    def create_daily_room(self, input_data: CreateRoomInput) -> Dict[str, Any]:
        """Generate a new Jitsi Meet WebRTC room URL"""
        try:
            # Unix timestamp for room expiry (metadata only)
            exp_time = int(time.time()) + (input_data.duration_minutes * 60)
            
            # Create a unique but readable Jitsi room name
            # Remove hyphens from UUID for cleaner Jitsi URLs
            clean_room_id = input_data.room_id.replace('-', '')
            room_name = f"InterviewPrepAgent_{clean_room_id}"
            
            # To avoid the "Waiting for moderator" screen on public meet.jit.si nodes, we pass these tenant configs.
            # Public Jitsi rooms automatically start when the first participant joins, sometimes requiring a display name.
            # `prejoinPageEnabled=false` skips the lobby.
            room_url = f"{self.base_url}/{room_name}#config.startWithAudioMuted=true&config.startWithVideoMuted=true&config.prejoinPageEnabled=false&userInfo.displayName=\"Interview Candidate\""
            
            logger.info(f"Created Jitsi room: {room_name}")
            
            return {
                "success": True,
                "room_url": room_url,
                "room_name": room_name,
                "expires_at": exp_time
            }
                
        except Exception as e:
            logger.error(f"❌ Error creating room: {e}")
            return {"success": False, "error": str(e)}

    def get_room_status(self, input_data: GetRoomStatusInput) -> Dict[str, Any]:
        """Get the status of a Jitsi room (Dummy implementation)"""
        # Jitsi rooms are ephemeral, so they technically always 'exist' as long as someone is in them.
        return {
            "success": True,
            "room": {
                "id": input_data.room_id,
                "status": "Available"
            }
        }

    def delete_room(self, input_data: DeleteRoomInput) -> Dict[str, Any]:
        """Delete a Jitsi room (Dummy implementation)"""
        # Jitsi rooms auto-delete when everyone leaves.
        return {
            "success": True,
            "message": f"Room {input_data.room_id} deleted successfully"
        }

    def list_active_rooms(self) -> Dict[str, Any]:
        """List active Jitsi rooms (Dummy implementation)"""
        # We don't track active Jitsi instances globally to save API usage.
        return {
            "success": True,
            "rooms": [],
            "total_count": 0
        }


# Singleton instance
room_mcp = RoomMCPServer()
