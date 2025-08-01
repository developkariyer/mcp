import datetime
import pytz
import os
from mcp_server import Tool, ToolDefinition, ToolFunction, ToolProperties, ToolParameter

def _parse_timezone(tz_str: str) -> datetime.tzinfo | None:
    try:
        return pytz.timezone(tz_str)
    except pytz.exceptions.UnknownTimeZoneError:
        try:
            if tz_str.startswith(('+', '-')) and ':' in tz_str:
                sign = -1 if tz_str.startswith('-') else 1
                parts = tz_str[1:].split(':')
                hours, minutes = int(parts[0]), int(parts[1])
                offset = datetime.timedelta(hours=hours, minutes=minutes)
                return datetime.timezone(sign * offset, name=tz_str)
        except (ValueError, IndexError):
            return None
    return None

def get_current_time(timezone: str | None = None) -> str:
    """Gets the current time and returns it as an ISO 8601 string."""
    tz_to_use = timezone or os.getenv("DEFAULT_TIMEZONE", "UTC")
    target_tz = _parse_timezone(tz_to_use)
    if target_tz is None:
        return f"Error: Invalid timezone '{tz_to_use}'. Use a name like 'Europe/London' or an offset like '-05:00'."
    utc_now = datetime.datetime.now(pytz.utc)
    local_time = utc_now.astimezone(target_tz)
    return local_time.isoformat()

_GET_TIME_TOOL_DEFINITION = ToolDefinition(
    function=ToolFunction(
        name="get_current_time",
        description="Get the current time for a given timezone and returns it in ISO 8601 format.",
        parameters=ToolProperties(
            properties={
                "timezone": ToolParameter(
                    type="string",
                    description="The timezone name (e.g., 'America/New_York') or UTC offset (e.g., '-05:00'). Defaults to the server's pre-configured timezone."
                )
            }
        )
    )
)

tool = Tool(
    definition=_GET_TIME_TOOL_DEFINITION,
    executor=get_current_time
)