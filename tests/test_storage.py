import os
import pytest
from alarm_clock.storage import StorageManager

def test_storage_initialization(tmp_path):
    filepath = tmp_path / "alarms.json"
    manager = StorageManager(str(filepath))
    
    # Should create an empty list on init
    assert filepath.exists()
    assert manager.load_raw() == []

def test_storage_save_and_load(tmp_path):
    filepath = tmp_path / "alarms.json"
    manager = StorageManager(str(filepath))
    
    test_data = [
        {"id": "1", "label": "Alarm 1"},
        {"id": "2", "label": "Alarm 2"}
    ]
    
    manager.save_raw(test_data)
    loaded = manager.load_raw()
    
    assert len(loaded) == 2
    assert loaded[0]["id"] == "1"
    assert loaded[1]["label"] == "Alarm 2"

def test_storage_corrupt_file_handling(tmp_path):
    filepath = tmp_path / "alarms.json"
    # Write invalid JSON manually
    with open(filepath, 'w') as f:
        f.write("{invalid json...")
        
    manager = StorageManager(str(filepath))
    # Should fall back to empty list rather than crashing
    assert manager.load_raw() == []
