"""
GWS Bridge — Python wrapper for Google Workspace CLI (gws).
Calls gws via subprocess for Gmail, Calendar, and Drive operations.

Designed by: Vera (architecture) + Dmitri (backend) + Nadia (security)
- 15-second timeout on all subprocess calls to prevent hangs
- Structured JSON output parsing
- Graceful fallback if gws is not installed

GWS CLI command reference:
  Email:    gws gmail +send --to EMAIL --subject SUBJECT --body TEXT
  Calendar: gws calendar +insert --summary TEXT --start TIME --end TIME --attendee EMAIL
  Events:   gws calendar events list --params '{"calendarId":"primary",...}'
  Inbox:    gws gmail +triage
"""
import subprocess
import json
import logging
import shutil
import base64
from typing import Dict, Any, Optional, List
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import os

from config import settings

logger = logging.getLogger(__name__)

# Cache the gws binary path
_gws_path: Optional[str] = None


def _get_gws_path() -> Optional[str]:
    """Find the gws binary. Cache the result for performance."""
    global _gws_path
    if _gws_path is not None:
        return _gws_path if _gws_path != "" else None

    custom = getattr(settings, 'gws_cli_path', 'gws')
    path = shutil.which(custom) or shutil.which('gws')
    _gws_path = path or ""
    if path:
        logger.info(f"✅ GWS CLI found at: {path}")
    else:
        logger.info("⚠️ GWS CLI not found. Install with: npm i -g @googleworkspace/cli")
    return path


def gws_available() -> bool:
    """Check if gws CLI is installed and responds."""
    path = _get_gws_path()
    if not path:
        return False
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def _run_gws(args: List[str], timeout: int = 15) -> Dict[str, Any]:
    """
    Execute a gws CLI command and return parsed JSON output.
    
    Dmitri's pattern: every external call gets a timeout budget.
    Nadia's rule: never log output that may contain email body content.
    """
    path = _get_gws_path()
    if not path:
        return {"success": False, "error": "GWS CLI not installed", "method": "gws"}

    cmd = [path] + args

    try:
        logger.debug(f"🔧 GWS: {' '.join(args[:3])}...")  # Log command, not data
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8"
        )

        if result.returncode != 0:
            error_output = result.stderr.strip() if result.stderr else result.stdout.strip()
            # Try to parse JSON error
            try:
                err_data = json.loads(error_output)
                error_msg = err_data.get("error", {}).get("message", error_output[:200])
            except (json.JSONDecodeError, TypeError):
                error_msg = error_output[:200] if error_output else f"Exit code {result.returncode}"
            logger.warning(f"⚠️ GWS command failed: {error_msg[:200]}")
            return {"success": False, "error": error_msg, "method": "gws"}

        # Parse JSON output
        output = result.stdout.strip()
        if output:
            try:
                data = json.loads(output)
                return {"success": True, "data": data, "method": "gws"}
            except json.JSONDecodeError:
                # Some commands return non-JSON success messages
                return {"success": True, "data": {"raw": output}, "method": "gws"}
        else:
            return {"success": True, "data": {}, "method": "gws"}

    except subprocess.TimeoutExpired:
        logger.error(f"❌ GWS command timed out after {timeout}s")
        return {"success": False, "error": f"GWS timed out after {timeout}s", "method": "gws"}
    except FileNotFoundError:
        logger.error("❌ GWS CLI binary not found at runtime")
        return {"success": False, "error": "GWS CLI not found", "method": "gws"}
    except Exception as e:
        logger.error(f"❌ GWS bridge error: {e}")
        return {"success": False, "error": str(e), "method": "gws"}


# ══════════════════════════════════════════════════════════════════
# GMAIL OPERATIONS
# ══════════════════════════════════════════════════════════════════

def gws_send_email(
    to_email: str,
    subject: str,
    body: str,
    is_html: bool = True,
    attachment_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send email via gws CLI.
    
    For plain text: uses 'gws gmail +send' helper (simple).
    For HTML/attachments: builds raw RFC 2822 message and uses 
    'gws gmail users messages send --json' with base64 encoded raw message.
    """
    if not is_html and not attachment_path:
        # Simple plain text — use the +send helper
        args = [
            "gmail", "+send",
            "--to", to_email,
            "--subject", subject,
            "--body", body,
            "--format", "json",
        ]
        result = _run_gws(args, timeout=15)
    else:
        # HTML or attachments — build raw MIME message
        msg = MIMEMultipart()
        msg["To"] = to_email
        msg["Subject"] = subject
        
        content_type = "html" if is_html else "plain"
        msg.attach(MIMEText(body, content_type))
        
        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                attachment = MIMEApplication(f.read(), _subtype="pdf")
                filename = os.path.basename(attachment_path)
                attachment.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(attachment)
        
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        
        json_body = json.dumps({"raw": raw_message})
        args = [
            "gmail", "users", "messages", "send",
            "--params", json.dumps({"userId": "me"}),
            "--json", json_body,
            "--format", "json",
        ]
        result = _run_gws(args, timeout=15)

    if result["success"]:
        logger.info(f"✅ Email sent via GWS CLI to {to_email}")
    return result


def gws_read_inbox(
    query: str = "",
    max_results: int = 10
) -> Dict[str, Any]:
    """Read inbox using gws gmail +triage helper or raw API."""
    # Use the +triage helper for simple inbox overview
    args = ["gmail", "+triage", "--format", "json"]
    return _run_gws(args, timeout=10)


# ══════════════════════════════════════════════════════════════════
# CALENDAR OPERATIONS
# ══════════════════════════════════════════════════════════════════

def gws_create_event(
    summary: str,
    start_time: str,
    end_time: str,
    attendees: Optional[List[str]] = None,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Create a calendar event via gws calendar +insert helper."""
    args = [
        "calendar", "+insert",
        "--summary", summary,
        "--start", start_time,
        "--end", end_time,
        "--format", "json",
    ]

    if attendees:
        for email in attendees:
            args.extend(["--attendee", email])

    if description:
        args.extend(["--description", description])

    result = _run_gws(args, timeout=15)

    if result["success"]:
        event_data = result.get("data", {})
        result["event_id"] = event_data.get("id", "")
        result["event_link"] = event_data.get("htmlLink", "")
        logger.info(f"✅ Calendar event created via GWS CLI: {summary}")
    return result


def gws_list_events(
    date_str: str,
    max_results: int = 20
) -> Dict[str, Any]:
    """List calendar events using gws calendar +agenda helper or raw API."""
    # Use raw API for date-based filtering
    time_min = f"{date_str}T00:00:00Z"
    time_max = f"{date_str}T23:59:59Z"

    params = {
        "calendarId": "primary",
        "timeMin": time_min,
        "timeMax": time_max,
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
    }

    args = [
        "calendar", "events", "list",
        "--params", json.dumps(params),
        "--format", "json",
    ]

    return _run_gws(args, timeout=10)


def gws_cancel_event(event_id: str) -> Dict[str, Any]:
    """Delete a calendar event via gws calendar events delete."""
    params = {
        "calendarId": "primary",
        "eventId": event_id,
        "sendUpdates": "all",
    }
    
    args = [
        "calendar", "events", "delete",
        "--params", json.dumps(params),
        "--format", "json",
    ]

    result = _run_gws(args, timeout=10)

    if result["success"]:
        logger.info(f"✅ Calendar event cancelled via GWS CLI: {event_id}")
    return result


def gws_reschedule_event(
    event_id: str,
    new_start_time: str,
    new_end_time: str
) -> Dict[str, Any]:
    """Reschedule an event via gws calendar events patch."""
    params = {
        "calendarId": "primary",
        "eventId": event_id,
        "sendUpdates": "all",
    }

    body = {
        "start": {"dateTime": new_start_time, "timeZone": "UTC"},
        "end": {"dateTime": new_end_time, "timeZone": "UTC"},
    }

    args = [
        "calendar", "events", "patch",
        "--params", json.dumps(params),
        "--json", json.dumps(body),
        "--format", "json",
    ]

    result = _run_gws(args, timeout=10)

    if result["success"]:
        logger.info(f"✅ Calendar event rescheduled via GWS CLI: {event_id}")
    return result
