import os
import fcntl
import json
from typing import List, Dict, Any

class StorageManager:
    """
    Manages loading and saving the alarm configuration list in alarms.json.
    Uses fcntl locking to ensure that concurrent read/write operations
    between the CLI process and the background daemon process do not conflict.
    """
    def __init__(self, filepath: str):
        self.filepath = os.path.abspath(filepath)
        # Ensure the parent directory exists
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        # Initialize the file if it does not exist or is empty
        if not os.path.exists(self.filepath) or os.path.getsize(self.filepath) == 0:
            self._initialize_empty()

    def _initialize_empty(self):
        with open(self.filepath, 'w') as f:
            # We don't strictly need a lock here since it's only initialization
            json.dump([], f, indent=4)

    def load_raw(self) -> List[Dict[str, Any]]:
        """
        Loads the raw list of alarm dictionaries with a shared lock (LOCK_SH).
        """
        if not os.path.exists(self.filepath):
            self._initialize_empty()
            return []

        with open(self.filepath, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                content = f.read()
                if not content.strip():
                    return []
                return json.loads(content)
            except json.JSONDecodeError:
                # If file is corrupted, fall back to empty list to avoid crashing
                return []
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def save_raw(self, alarms_data: List[Dict[str, Any]]) -> None:
        """
        Saves the list of alarm dictionaries with an exclusive lock (LOCK_EX).
        Opens file in read-write ('r+') mode to avoid truncating before acquiring lock.
        """
        if not os.path.exists(self.filepath):
            self._initialize_empty()

        with open(self.filepath, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                # Position pointer to start, dump JSON, then truncate remaining old contents
                f.seek(0)
                json.dump(alarms_data, f, indent=4)
                f.truncate()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
