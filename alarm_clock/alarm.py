import re
import uuid
import datetime
from typing import Dict, Any, Optional

class AlarmStatus:
    PENDING = "PENDING"
    RINGING = "RINGING"
    SNOOZED = "SNOOZED"
    DISMISSED = "DISMISSED"
    MISSED = "MISSED"

def parse_time_input(time_str: str) -> datetime.datetime:
    """
    Parses various time input strings:
    - Relative times: e.g. "+10s", "+5m", "+1h", "+1h30m"
    - Absolute times: e.g. "15:45", "08:30", "3:30 PM", "3:30PM"
    - ISO datetime strings (for restoring saved state or specific future dates)
    Returns a datetime object in local time.
    """
    now = datetime.datetime.now()
    time_str = time_str.strip()

    # 1. Relative time check (starts with '+')
    if time_str.startswith('+'):
        # Match pattern like +2h30m10s, +5m, +10s, etc.
        pattern = re.compile(r'^\+(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$')
        match = pattern.match(time_str)
        if not match:
            raise ValueError("Invalid relative time format. Use formats like +10s, +5m, +1h, +1h30m")
        
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0
        
        if hours == 0 and minutes == 0 and seconds == 0:
            raise ValueError("Relative time must be greater than zero.")
            
        delta = datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds)
        return now + delta

    # 2. Absolute time check (try common times)
    formats = [
        "%H:%M",        # 15:45
        "%H:%M:%S",     # 15:45:00
        "%I:%M %p",     # 03:45 PM / 3:45 PM
        "%I:%M%p",      # 03:45PM / 3:45PM
        "%I %p",        # 3 PM
        "%I%p",         # 3PM
    ]
    
    for fmt in formats:
        try:
            parsed_time = datetime.datetime.strptime(time_str, fmt)
            # Combine parsed hour/minute/second with today's date
            target = now.replace(
                hour=parsed_time.hour, 
                minute=parsed_time.minute, 
                second=parsed_time.second, 
                microsecond=0
            )
            # If target time is in the past for today, schedule it for tomorrow!
            if target <= now:
                target += datetime.timedelta(days=1)
            return target
        except ValueError:
            continue
            
    # 3. ISO Datetime fallback
    try:
        return datetime.datetime.fromisoformat(time_str)
    except ValueError:
        pass
        
    raise ValueError(
        f"Could not parse time format: '{time_str}'.\n"
        "Supported formats:\n"
        "  - Relative: +30s, +15m, +1h, +1h30m\n"
        "  - Absolute: 14:30, 2:30 PM, 2:30PM, 9 PM\n"
        "  - ISO Date: 2026-06-04T15:45:00"
    )

class Alarm:
    def __init__(
        self,
        trigger_time: datetime.datetime,
        label: str = "Alarm",
        sound_path: Optional[str] = None,
        alarm_id: Optional[str] = None,
        status: str = AlarmStatus.PENDING,
        snooze_count: int = 0,
        snooze_duration_minutes: int = 5,
        original_time: Optional[datetime.datetime] = None
    ):
        self.id = alarm_id if alarm_id else str(uuid.uuid4())[:8]  # Short prefix of UUID is sufficient and user friendly
        self.trigger_time = trigger_time
        self.label = label
        self.sound_path = sound_path
        self.status = status
        self.snooze_count = snooze_count
        self.snooze_duration_minutes = snooze_duration_minutes
        self.original_time = original_time if original_time else trigger_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "trigger_time": self.trigger_time.isoformat(),
            "label": self.label,
            "sound_path": self.sound_path,
            "status": self.status,
            "snooze_count": self.snooze_count,
            "snooze_duration_minutes": self.snooze_duration_minutes,
            "original_time": self.original_time.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Alarm":
        return cls(
            alarm_id=data["id"],
            trigger_time=datetime.datetime.fromisoformat(data["trigger_time"]),
            label=data["label"],
            sound_path=data.get("sound_path"),
            status=data["status"],
            snooze_count=data.get("snooze_count", 0),
            snooze_duration_minutes=data.get("snooze_duration_minutes", 5),
            original_time=datetime.datetime.fromisoformat(data["original_time"]) if "original_time" in data else None
        )

    def snooze(self) -> None:
        """Snoozes the alarm by updating status and adding snooze duration to trigger time."""
        self.snooze_count += 1
        delta = datetime.timedelta(minutes=self.snooze_duration_minutes)
        self.trigger_time = datetime.datetime.now() + delta
        self.status = AlarmStatus.SNOOZED

    def dismiss(self) -> None:
        """Dismisses the alarm."""
        self.status = AlarmStatus.DISMISSED
