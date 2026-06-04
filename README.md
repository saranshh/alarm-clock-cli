# macOS Alarm Clock CLI

A robust, dependency-light Python Command-Line Interface (CLI) alarm clock application built specifically for macOS. The application is split into a **Client (CLI)** and a **Background Daemon** which communicate asynchronously through a locked state file.

---

## 🛠 Architectural Design & Engineering Decisions

When designing this CLI alarm clock, the primary goals were **reliability**, **low resource footprint**, **fault tolerance (sleep recovery)**, and **macOS-native user experience**. Here are the major architectural decisions and their technical rationale:

### 1. IPC & State Synchronization: Locked JSON File vs. Sockets
*   **Decision**: Use a single JSON database (`alarms.json`) wrapped in Unix-standard file locking (`fcntl`) to serve as the IPC medium and the Single Source of Truth.
*   **Rationale**:
    *   *No Port Conflicts*: Running local servers (TCP/UDP sockets) introduces port collision risks, firewall prompts, and security surfaces.
    *   *Decoupled Design*: The CLI client updates the status of an alarm (e.g. to `DISMISSED` or `SNOOZED`) in `alarms.json`. The daemon polls the file, observes the state transition, and terminates the active playback process.
    *   *Instant State Persistence*: If the background daemon crashes or the computer restarts, restarting the daemon instantly recovers all pending/ringing/snoozed alarms because the state is persisted.
    *   *Concurrency Safety*: We employ `fcntl.flock(f, fcntl.LOCK_EX)` during writes to ensure absolute thread and process safety if the user runs CLI commands while the daemon is actively writing updates.

### 2. Daemon Lifecycle: Detached Subprocesses & PID Checks
*   **Decision**: Spawning the daemon via Python's `subprocess.Popen` with `start_new_session=True` and monitoring status using `os.kill(pid, 0)`.
*   **Rationale**:
    *   *Mac Compatibility*: Classic double-fork Unix daemonization can exhibit erratic behavior on macOS due to modern macOS system security constraints.
    *   *Detached Process*: `start_new_session=True` detaches the child process from the terminal window's session group, ensuring the daemon keeps running even if the terminal window is closed.
    *   *Reliable Status Verification*: Instead of relying solely on the existence of a `.alarm_daemon.pid` file, we check process survival using `os.kill(pid, 0)`. This prevents "stale PID file" false positives after a system crash.

### 3. Media & Alerts: Native macOS Integration
*   **Decision**: Use native system utilities `/usr/bin/afplay` for audio playback and AppleScript `osascript` for native desktop notifications.
*   **Rationale**:
    *   *Zero Heavy Dependencies*: Python libraries like `pyaudio` or `pygame` require C-extensions or compilation, which can easily fail on different machines (e.g., M1/M2/M3 Apple Silicon vs Intel).
    *   *Native UX*: Using `osascript` displays a clean, OS-native banner in the top-right corner of the user's screen.
    *   *Audio Control*: Spawning `afplay` as a separate subprocess lets the daemon stop audio playback instantly via process signals (e.g., `process.terminate()`) when the user runs `snooze` or `dismiss`.

---

## ⚡ Edge-Case & Failure Handling

Designing for real-world scenarios required handling the common failures of alarm applications:

### 💤 Missed Alarms (Computer Sleep or Daemon Down)
*   **Problem**: If the user closes their laptop and the computer goes to sleep, or if the daemon is stopped, the scheduled trigger time of an alarm may pass without the alarm ringing.
*   **Solution**: We define a **5-minute threshold**. When the daemon boots or wakes from sleep:
    *   If an alarm's scheduled time is in the past, but by **less than 5 minutes**, the daemon triggers it immediately.
    *   If the scheduled time is in the past by **more than 5 minutes**, the daemon marks it as `MISSED` and fires a notification notifying the user that they missed the alarm, avoiding unexpected loud rings hours after the fact.

### ⏰ Absolute Time Parsing (Past vs. Tomorrow)
*   **Problem**: If it is 6:00 PM and the user schedules an alarm for `8:00 AM`, setting it for "today" would trigger it immediately as a past/missed alarm.
*   **Solution**: If an absolute time (e.g., `8:00 AM`, `14:30`) translates to a time that has already passed today, the application automatically schedules the alarm for **tomorrow** at that time.

### 🔄 Concurrent Rings
*   **Problem**: Multiple alarms scheduled for the exact same time.
*   **Solution**: The daemon runs independent players and triggers notifications concurrently for each active alarm. It maps running players using `alarm.id` to track and control each ringing instance independently.

---

## 🚀 Installation & Setup

1. Clone or extract the repository:
   ```bash
   cd alarm-clock-cli
   ```

2. Install dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```
   *(Note: The only core dependency is `rich` for CLI aesthetics and `pytest` for running tests).*

3. Run automated tests to verify the setup:
   ```bash
   python3 -m pytest
   ```

---

## 📖 Command Reference

The tool is invoked via `python3 main.py <command>`.

### Daemon Control
*   **`python3 main.py start`**: Starts the background alarm scheduler process in detached mode.
*   **`python3 main.py stop`**: Gracefully stops the background scheduler.
*   **`python3 main.py status`**: Shows if the background daemon is active and summarizes pending/ringing/total alarms.

### Alarm Management
*   **`python3 main.py add <time> [options]`**: Schedules a new alarm.
    *   *Relative Time*: `+10s` (10 seconds), `+5m` (5 minutes), `+1h30m` (1 hour 30 minutes).
    *   *Absolute Time*: `15:45` (24h format), `3:45 PM` (12h format).
    *   *Options*:
        *   `-l, --label <text>`: Give the alarm a custom title (e.g., `--label "Stand up"`).
        *   `-s, --sound <path>`: Supply a custom audio file path (supports MP3, WAV, AIFF).
        *   `-z, --snooze <minutes>`: Specify a custom snooze duration (defaults to 5 minutes).
*   **`python3 main.py list`**: Renders a beautiful visual table of all registered, ringing, pending, and past alarms.
*   **`python3 main.py remove <id>`**: Cancels/deletes the alarm with the given ID.

### Interaction
*   **`python3 main.py snooze <id>`**: Snoozes a currently ringing alarm for the configured duration (snooze count increments).
*   **`python3 main.py dismiss <id>`**: Turns off a currently ringing alarm.

---

## ✅ Testing & Validation

### Automated Unit Tests
We use `pytest` to cover core functionality. The suite is located in the `tests/` directory:
*   `tests/test_alarm.py`: Tests relative/absolute parsing, past time rollovers, status updates, and JSON serialization.
*   `tests/test_storage.py`: Tests file creation, writing, reading, and corrupted/malformed file recovery.

To run:
```bash
python3 -m pytest
```

### Manual Integration Scenarios Verified
1.  **Daemon Lifecycle**: Ran `start`, checked `status` (RUNNING), verified PID, ran `stop`, verified PID file was deleted and daemon shut down cleanly.
2.  **Ringing & Dismiss**: Added an alarm for `+10s`, started the daemon, verified the sound and notification fired at the 10s mark, ran `dismiss <id>`, and verified the sound stopped instantly and the alarm state changed to `DISMISSED`.
3.  **Snooze**: Added an alarm for `+5s`, let it ring, ran `snooze <id>`, verified sound stopped, verified the alarm was rescheduled to current time + 5 minutes and marked as `SNOOZED`.
4.  **Missed Recovery**: Created an alarm, stopped the daemon, manually edited the JSON file to backdate the trigger time by 6 minutes, started the daemon, and verified the daemon marked it as `MISSED` and sent a missed notification without playing any audio.
