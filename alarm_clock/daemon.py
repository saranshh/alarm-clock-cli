import os
import time
import signal
import sys
import datetime
from typing import Dict

from alarm_clock.storage import StorageManager
from alarm_clock.alarm import Alarm, AlarmStatus
from alarm_clock.sound import AlarmPlayer
from alarm_clock.notification import send_notification

# Check if process is running by sending signal 0
def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Running but owned by another user
        return True
    except Exception:
        return False

class AlarmDaemon:
    """
    Background daemon process that continuously polls the alarms database,
    triggers ringing alarms, spawns audio players, and sends system notifications.
    """
    def __init__(self, storage_manager: StorageManager, pid_filepath: str):
        self.storage = storage_manager
        self.pid_filepath = os.path.abspath(pid_filepath)
        self.active_players: Dict[str, AlarmPlayer] = {}
        self.running = True

    def handle_shutdown(self, signum, frame):
        """Gracefully handle termination signals."""
        self.running = False

    def run(self) -> None:
        # Verify another daemon is not already running
        if os.path.exists(self.pid_filepath):
            try:
                with open(self.pid_filepath, 'r') as f:
                    pid = int(f.read().strip())
                if is_pid_running(pid):
                    print(f"Error: Daemon is already running with PID {pid}.", file=sys.stderr)
                    sys.exit(1)
            except ValueError:
                # Corrupt PID file, we'll overwrite it
                pass

        # Write our PID to file
        with open(self.pid_filepath, 'w') as f:
            f.write(str(os.getpid()))

        # Register signal handlers for clean exit
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGINT, self.handle_shutdown)

        try:
            while self.running:
                self.tick()
                time.sleep(1)
        finally:
            self.cleanup()

    def tick(self) -> None:
        """Single evaluation tick of the daemon loop."""
        try:
            raw_alarms = self.storage.load_raw()
        except Exception as e:
            # Log error and retry next tick if file read fails (e.g. temporary lock contention)
            print(f"[{datetime.datetime.now()}] Storage read error: {e}", file=sys.stderr)
            return

        current_alarms = {a["id"]: Alarm.from_dict(a) for a in raw_alarms}
        current_time = datetime.datetime.now()

        # 1. Stop players for alarms that were dismissed, snoozed, or deleted via the CLI
        ids_to_stop = []
        for alarm_id in list(self.active_players.keys()):
            if alarm_id not in current_alarms:
                # Alarm was deleted
                ids_to_stop.append(alarm_id)
            else:
                alarm = current_alarms[alarm_id]
                # If user snoozed or dismissed it via CLI, stop playing
                if alarm.status not in (AlarmStatus.RINGING,):
                    ids_to_stop.append(alarm_id)

        for alarm_id in ids_to_stop:
            self.active_players[alarm_id].stop()
            del self.active_players[alarm_id]

        # 2. Check which alarms need to trigger or continue ringing
        state_changed = False

        for alarm_id, alarm in current_alarms.items():
            if alarm.status in (AlarmStatus.PENDING, AlarmStatus.SNOOZED):
                # Trigger time has arrived or passed
                if alarm.trigger_time <= current_time:
                    time_diff = current_time - alarm.trigger_time
                    # If trigger time is too far in the past (e.g. computer slept or daemon was down)
                    if time_diff > datetime.timedelta(minutes=5):
                        alarm.status = AlarmStatus.MISSED
                        state_changed = True
                        send_notification(
                            title="Missed Alarm",
                            message=f"Alarm '{alarm.label}' (scheduled for {alarm.trigger_time.strftime('%I:%M %p')}) was missed."
                        )
                    else:
                        # Trigger the alarm
                        alarm.status = AlarmStatus.RINGING
                        state_changed = True
                        
                        send_notification(
                            title="Alarm Ringing",
                            message=f"Alarm: {alarm.label}"
                        )
                        
                        player = AlarmPlayer(sound_path=alarm.sound_path)
                        player.start()
                        self.active_players[alarm.id] = player

            elif alarm.status == AlarmStatus.RINGING:
                # Ensure the sound loops if the alarm is still ringing
                if alarm.id in self.active_players:
                    player = self.active_players[alarm.id]
                    if not player.is_playing():
                        player.start()
                else:
                    # If daemon restarted during a ring, restart the sound
                    player = AlarmPlayer(sound_path=alarm.sound_path)
                    player.start()
                    self.active_players[alarm.id] = player

        # 3. Save state back to disk if any alarms changed status
        if state_changed:
            try:
                updated_raw = [a.to_dict() for a in current_alarms.values()]
                self.storage.save_raw(updated_raw)
            except Exception as e:
                print(f"[{datetime.datetime.now()}] Storage write error: {e}", file=sys.stderr)

    def cleanup(self) -> None:
        """Stops all players and deletes the PID file."""
        for player in self.active_players.values():
            try:
                player.stop()
            except Exception:
                pass
        self.active_players.clear()

        if os.path.exists(self.pid_filepath):
            try:
                os.remove(self.pid_filepath)
            except Exception:
                pass
