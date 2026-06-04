import os
import sys
import signal
import time
import argparse
import datetime
import subprocess
from typing import List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from alarm_clock.storage import StorageManager
from alarm_clock.alarm import Alarm, AlarmStatus, parse_time_input
from alarm_clock.daemon import AlarmDaemon, is_pid_running

# Global configuration paths (all stored relative to project root or current dir)
DB_FILE = "alarms.json"
PID_FILE = ".alarm_daemon.pid"
LOG_FILE = ".alarm_daemon.log"

console = Console()

def get_storage() -> StorageManager:
    return StorageManager(DB_FILE)

def format_remaining(dt: datetime.datetime) -> str:
    """Computes a human-readable remaining time string."""
    now = datetime.datetime.now()
    if dt <= now:
        return "past"
    diff = dt - now
    days = diff.days
    hours, remainder = divmod(diff.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
        
    return "in " + " ".join(parts)

def handle_start(args) -> None:
    """Starts the alarm daemon in the background."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            if is_pid_running(pid):
                console.print(f"[bold yellow]Daemon is already running with PID {pid}.[/bold yellow]")
                return
        except ValueError:
            pass

    console.print("[bold green]Starting alarm background daemon...[/bold green]")
    
    # Detach daemon process and direct output to LOG_FILE
    log_file = open(LOG_FILE, "a")
    # Command to run self with run-daemon subcommand
    cmd = [sys.executable, sys.argv[0], "run-daemon"]
    
    try:
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True
        )
        # Give daemon a brief moment to write its PID
        time.sleep(0.5)
        
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                new_pid = f.read().strip()
            console.print(f"[bold green]✓ Daemon successfully started in background (PID: {new_pid}).[/bold green]")
            console.print(f"[dim]Logs are written to {LOG_FILE}[/dim]")
        else:
            console.print("[bold red]✗ Daemon spawned but PID file was not created. Check logs.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]✗ Failed to start daemon: {e}[/bold red]")

def handle_stop(args) -> None:
    """Stops the running daemon."""
    if not os.path.exists(PID_FILE):
        console.print("[bold yellow]Daemon is not running (PID file not found).[/bold yellow]")
        return

    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
    except ValueError:
        console.print("[bold red]Corrupt PID file. Deleting...[/bold red]")
        os.remove(PID_FILE)
        return

    if not is_pid_running(pid):
        console.print("[bold yellow]Daemon process is not active, cleaning up PID file.[/bold yellow]")
        os.remove(PID_FILE)
        return

    console.print(f"[yellow]Stopping daemon (PID {pid})...[/yellow]")
    
    # Try SIGTERM first
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
        
    # Wait for process to exit
    for _ in range(20):
        if not is_pid_running(pid):
            break
        time.sleep(0.1)
        
    # If still running, force kill
    if is_pid_running(pid):
        console.print("[bold red]Daemon did not exit. Force terminating...[/bold red]")
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    # Ensure PID file is removed
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
            
    console.print("[bold green]✓ Daemon stopped.[/bold green]")

def handle_status(args) -> None:
    """Displays daemon process status and general statistics."""
    running = False
    pid_str = "N/A"
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            if is_pid_running(pid):
                running = True
                pid_str = str(pid)
        except ValueError:
            pass

    # Read alarm counts
    storage = get_storage()
    alarms = [Alarm.from_dict(d) for d in storage.load_raw()]
    
    ringing_count = sum(1 for a in alarms if a.status == AlarmStatus.RINGING)
    pending_count = sum(1 for a in alarms if a.status in (AlarmStatus.PENDING, AlarmStatus.SNOOZED))
    total_count = len(alarms)

    if running:
        status_markup = f"[bold green]RUNNING[/bold green] [dim](PID: {pid_str})[/dim]"
    else:
        status_markup = "[bold red]STOPPED[/bold red]"

    summary_panel = Panel(
        f"Daemon Status: {status_markup}\n"
        f"Active Rings:  [bold magenta]{ringing_count}[/bold magenta]\n"
        f"Pending Alarms: [bold green]{pending_count}[/bold green]\n"
        f"Total Alarms:   {total_count}",
        title="⏰ Alarm Clock Status",
        expand=False
    )
    console.print(summary_panel)
    
    if not running:
        console.print("[dim italic]Hint: Start the background scheduler with 'python main.py start' to hear your alarms.[/dim italic]")

def handle_add(args) -> None:
    """Adds a new alarm to the list."""
    try:
        trigger_time = parse_time_input(args.time)
    except ValueError as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        sys.exit(1)

    # Optional custom sound verification
    sound_path = args.sound
    if sound_path and not os.path.exists(sound_path):
        console.print(f"[bold yellow]Warning: Sound file '{sound_path}' not found. Using default ringtone.[/bold yellow]")
        sound_path = None

    storage = get_storage()
    raw_alarms = storage.load_raw()
    alarms = [Alarm.from_dict(d) for d in raw_alarms]

    new_alarm = Alarm(
        trigger_time=trigger_time,
        label=args.label,
        sound_path=sound_path,
        snooze_duration_minutes=args.snooze
    )

    alarms.append(new_alarm)
    storage.save_raw([a.to_dict() for a in alarms])

    console.print(Panel(
        f"Alarm [bold cyan]{new_alarm.id}[/bold cyan] set successfully!\n"
        f"Time:       [bold green]{new_alarm.trigger_time.strftime('%Y-%m-%d %I:%M:%S %p')}[/bold green]\n"
        f"Triggers:   [bold yellow]{format_remaining(new_alarm.trigger_time)}[/bold yellow]\n"
        f"Label:      {new_alarm.label}\n"
        f"Snooze:     {new_alarm.snooze_duration_minutes} min",
        title="Alarm Scheduled"
    ))

def handle_list(args) -> None:
    """Lists all alarms."""
    storage = get_storage()
    raw_alarms = storage.load_raw()
    if not raw_alarms:
        console.print("[yellow]No alarms found. Set one with 'python main.py add <time>'[/yellow]")
        return

    alarms = [Alarm.from_dict(d) for d in raw_alarms]
    # Sort: pending first, then by trigger time
    alarms.sort(key=lambda a: (a.status not in (AlarmStatus.RINGING, AlarmStatus.PENDING, AlarmStatus.SNOOZED), a.trigger_time))

    table = Table(title="⏰ Alarm Clock Registry")
    table.add_column("ID", style="cyan")
    table.add_column("Scheduled Time", style="white")
    table.add_column("Remaining / Status", style="yellow")
    table.add_column("Label", style="magenta")
    table.add_column("Snooze Count", style="blue", justify="right")
    table.add_column("Ringtone", style="dim green")

    for a in alarms:
        # Determine status styling
        if a.status == AlarmStatus.RINGING:
            status_str = "[bold red blink]🔔 RINGING![/bold red blink]"
            time_str = f"[bold red]{a.trigger_time.strftime('%I:%M:%S %p')}[/bold red]"
        elif a.status == AlarmStatus.PENDING:
            status_str = f"[green]{format_remaining(a.trigger_time)}[/green]"
            time_str = a.trigger_time.strftime("%I:%M:%S %p")
        elif a.status == AlarmStatus.SNOOZED:
            status_str = f"[cyan]{format_remaining(a.trigger_time)} (Snoozed)[/cyan]"
            time_str = a.trigger_time.strftime("%I:%M:%S %p")
        elif a.status == AlarmStatus.MISSED:
            status_str = "[bold yellow]⚠️ MISSED[/bold yellow]"
            time_str = a.trigger_time.strftime("%I:%M:%S %p")
        else:  # DISMISSED
            status_str = "[dim]DISMISSED[/dim]"
            time_str = f"[dim]{a.trigger_time.strftime('%I:%M %p')}[/dim]"

        ringtone = os.path.basename(a.sound_path) if a.sound_path else "Default"

        table.add_row(
            a.id,
            time_str,
            status_str,
            a.label,
            str(a.snooze_count),
            ringtone
        )

    console.print(table)

def handle_remove(args) -> None:
    """Removes an alarm from the database."""
    storage = get_storage()
    raw_alarms = storage.load_raw()
    alarms = [Alarm.from_dict(d) for d in raw_alarms]

    filtered_alarms = [a for a in alarms if a.id != args.id]
    
    if len(filtered_alarms) == len(alarms):
        console.print(f"[bold red]Error: Alarm with ID '{args.id}' not found.[/bold red]")
        sys.exit(1)

    storage.save_raw([a.to_dict() for a in filtered_alarms])
    console.print(f"[bold green]✓ Alarm '{args.id}' successfully removed.[/bold green]")

def handle_snooze(args) -> None:
    """Snoozes an active ringing alarm."""
    storage = get_storage()
    raw_alarms = storage.load_raw()
    alarms = [Alarm.from_dict(d) for d in raw_alarms]

    alarm = next((a for a in alarms if a.id == args.id), None)
    if not alarm:
        console.print(f"[bold red]Error: Alarm with ID '{args.id}' not found.[/bold red]")
        sys.exit(1)

    if alarm.status != AlarmStatus.RINGING:
        console.print(f"[bold red]Error: Alarm '{args.id}' is not currently ringing (status is {alarm.status}).[/bold red]")
        sys.exit(1)

    alarm.snooze()
    storage.save_raw([a.to_dict() for a in alarms])
    
    console.print(
        f"[bold green]✓ Alarm '{args.id}' snoozed for {alarm.snooze_duration_minutes} minutes.[/bold green]\n"
        f"Next ring scheduled for: [bold yellow]{alarm.trigger_time.strftime('%I:%M:%S %p')}[/bold yellow] "
        f"({format_remaining(alarm.trigger_time)})"
    )

def handle_dismiss(args) -> None:
    """Dismisses an active ringing alarm."""
    storage = get_storage()
    raw_alarms = storage.load_raw()
    alarms = [Alarm.from_dict(d) for d in raw_alarms]

    alarm = next((a for a in alarms if a.id == args.id), None)
    if not alarm:
        console.print(f"[bold red]Error: Alarm with ID '{args.id}' not found.[/bold red]")
        sys.exit(1)

    if alarm.status != AlarmStatus.RINGING:
        console.print(f"[bold red]Error: Alarm '{args.id}' is not currently ringing (status is {alarm.status}).[/bold red]")
        sys.exit(1)

    alarm.dismiss()
    storage.save_raw([a.to_dict() for a in alarms])
    console.print(f"[bold green]✓ Alarm '{args.id}' dismissed.[/bold green]")

def handle_run_daemon(args) -> None:
    """Runs the daemon service in the foreground (used internally or for debugging)."""
    storage = get_storage()
    daemon = AlarmDaemon(storage, PID_FILE)
    console.print("[bold green]Starting alarm daemon in foreground. Press Ctrl+C to stop.[/bold green]")
    daemon.run()

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alarm Clock CLI - A robust command-line scheduler & background notification daemon."
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands")

    # Start daemon
    subparsers.add_parser("start", help="Start the background alarm daemon process")
    
    # Stop daemon
    subparsers.add_parser("stop", help="Stop the background alarm daemon process")
    
    # Status daemon
    subparsers.add_parser("status", help="Show the current daemon status and statistics")

    # Add alarm
    parser_add = subparsers.add_parser("add", help="Add a new alarm")
    parser_add.add_argument("time", type=str, help="Absolute time (e.g. 15:45, 8:00 AM) or relative (e.g. +10s, +5m, +1h)")
    parser_add.add_argument("-l", "--label", type=str, default="Alarm", help="Name/Label of the alarm")
    parser_add.add_argument("-s", "--sound", type=str, default=None, help="Custom sound file path (.mp3, .wav, .aiff)")
    parser_add.add_argument("-z", "--snooze", type=int, default=5, help="Snooze duration in minutes (default: 5)")

    # List alarms
    subparsers.add_parser("list", help="List all scheduled, active, and past alarms")

    # Remove alarm
    parser_remove = subparsers.add_parser("remove", help="Remove/Cancel an alarm")
    parser_remove.add_argument("id", type=str, help="The ID of the alarm to remove")

    # Snooze alarm
    parser_snooze = subparsers.add_parser("snooze", help="Snooze a ringing alarm")
    parser_snooze.add_argument("id", type=str, help="The ID of the ringing alarm to snooze")

    # Dismiss alarm
    parser_dismiss = subparsers.add_parser("dismiss", help="Dismiss/Stop a ringing alarm")
    parser_dismiss.add_argument("id", type=str, help="The ID of the ringing alarm to dismiss")

    # Foreground daemon run (hidden from user help to avoid confusion, but accessible)
    subparsers.add_parser("run-daemon", help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Map commands to handlers
    handlers = {
        "start": handle_start,
        "stop": handle_stop,
        "status": handle_status,
        "add": handle_add,
        "list": handle_list,
        "remove": handle_remove,
        "snooze": handle_snooze,
        "dismiss": handle_dismiss,
        "run-daemon": handle_run_daemon
    }

    if args.command in handlers:
        handlers[args.command](args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
