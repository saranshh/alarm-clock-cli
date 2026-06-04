import datetime
import pytest
from alarm_clock.alarm import Alarm, AlarmStatus, parse_time_input

def test_parse_relative_time():
    # Test +seconds
    t1 = parse_time_input("+10s")
    diff = t1 - datetime.datetime.now()
    assert 9 <= diff.total_seconds() <= 11

    # Test +minutes
    t2 = parse_time_input("+5m")
    diff2 = t2 - datetime.datetime.now()
    assert 299 <= diff2.total_seconds() <= 301

    # Test +hours and +minutes mixed
    t3 = parse_time_input("+1h30m")
    diff3 = t3 - datetime.datetime.now()
    assert 5399 <= diff3.total_seconds() <= 5401

def test_parse_absolute_time():
    now = datetime.datetime.now()
    
    # Schedule a future time today
    future_hour = (now.hour + 1) % 24
    if future_hour == 0:
        # Avoid rollover boundary issues for absolute time tests
        future_hour = 12
    
    time_str = f"{future_hour:02d}:00"
    t = parse_time_input(time_str)
    
    # If the target hour is actually behind us (e.g. now.hour + 1 rolled over to 0, which is < now.hour)
    if future_hour < now.hour:
        assert t.day == (now + datetime.timedelta(days=1)).day
    else:
        assert t.day == now.day
    assert t.hour == future_hour
    assert t.minute == 0

def test_parse_past_time_rollover():
    now = datetime.datetime.now()
    # Find an hour that is in the past for today
    past_hour = (now.hour - 1) % 24
    time_str = f"{past_hour:02d}:00"
    
    t = parse_time_input(time_str)
    
    # Must be scheduled for tomorrow
    tomorrow = now + datetime.timedelta(days=1)
    assert t.day == tomorrow.day
    assert t.hour == past_hour
    assert t.minute == 0

def test_parse_invalid_time():
    with pytest.raises(ValueError):
        parse_time_input("invalid-time-format")
    with pytest.raises(ValueError):
        parse_time_input("+0s")
    with pytest.raises(ValueError):
        parse_time_input("+5x")

def test_alarm_status_transitions():
    now = datetime.datetime.now()
    alarm = Alarm(trigger_time=now, label="Test", snooze_duration_minutes=2)
    
    assert alarm.status == AlarmStatus.PENDING
    assert alarm.snooze_count == 0
    
    # Snooze
    alarm.snooze()
    assert alarm.status == AlarmStatus.SNOOZED
    assert alarm.snooze_count == 1
    # Trigger time should be updated to future
    assert alarm.trigger_time > now

    # Dismiss
    alarm.dismiss()
    assert alarm.status == AlarmStatus.DISMISSED

def test_serialization():
    t = datetime.datetime.now().replace(microsecond=0)
    alarm = Alarm(trigger_time=t, label="Testing Serialization", sound_path="/some/sound.mp3")
    
    data = alarm.to_dict()
    assert data["label"] == "Testing Serialization"
    assert data["sound_path"] == "/some/sound.mp3"
    assert data["status"] == AlarmStatus.PENDING
    
    restored = Alarm.from_dict(data)
    assert restored.id == alarm.id
    assert restored.label == alarm.label
    assert restored.sound_path == alarm.sound_path
    assert restored.trigger_time == t
    assert restored.status == alarm.status
