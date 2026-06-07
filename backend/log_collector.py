import os
import re
import platform
from datetime import datetime
from database import Session, SyslogEntry

LOG_PATHS = {
    "linux": ["/var/log/syslog", "/var/log/kern.log", "/var/log/dmesg"],
    "darwin": ["/var/log/system.log"],
    "windows": []
}

CRASH_PATTERNS = [
    r"kernel panic",
    r"Out of memory.*Killed process",
    r"segfault",
    r"general protection fault",
    r"BUG:",
    r"Call Trace:",
    r"BSOD|STOP: 0x",
    r"critical error",
    r"fatal error",
]

WARNING_PATTERNS = [
    r"(high|excessive) (memory|cpu|disk) (usage|pressure)",
    r"(temperature|thermal).*(critical|warning|throttling)",
    r"disk.*error",
    r"memory.*error",
    r"failed to allocate",
    r"soft lockup",
    r"hung_task",
]

def simulate_logs():
    return [
        "kernel: Out of memory: Killed process 1234 (chrome) total-vm:4096000kB",
        "WARNING: high memory usage detected on process explorer.exe",
        "disk error detected on drive C:",
        "thermal: temperature critical, throttling CPU",
        "fatal error in application crashtest.exe",
        "WARNING: failed to allocate memory block 512MB",
        "System: normal operation",
        "INFO: user logged in",
    ]

def read_windows_event_logs():
    entries = []
    try:
        import win32evtlog
        import win32con
        import win32evtlogutil

        logs_to_check = ["System", "Application"]
        for log_name in logs_to_check:
            hand = win32evtlog.OpenEventLog(None, log_name)
            flags = (win32evtlog.EVENTLOG_BACKWARDS_READ |
                     win32evtlog.EVENTLOG_SEQUENTIAL_READ)
            count = 0
            while count < 200:
                events = win32evtlog.ReadEventLog(hand, flags, 0)
                if not events:
                    break
                for event in events:
                    if event.EventType in (
                        win32con.EVENTLOG_ERROR_TYPE,
                        win32con.EVENTLOG_WARNING_TYPE
                    ):
                        try:
                            msg = win32evtlogutil.SafeFormatMessage(event, log_name)
                        except:
                            msg = str(event.StringInserts) if event.StringInserts else "No message"
                        timestamp = event.TimeGenerated.Format()
                        level = "ERROR" if event.EventType == win32con.EVENTLOG_ERROR_TYPE else "WARN"
                        entries.append(f"[{log_name}] [{level}] [{timestamp}] {msg}")
                        count += 1
            win32evtlog.CloseEventLog(hand)
        print(f"[log_collector] Read {len(entries)} real Windows Event Log entries")
    except ImportError:
        print("[Warning] pywin32 not installed. Using simulated logs.")
        entries = simulate_logs()
    except Exception as e:
        print(f"[Warning] Could not read Windows Event Log: {e}")
        entries = simulate_logs()
    return entries

def read_recent_logs(lines=500):
    system = platform.system().lower()
    paths = LOG_PATHS.get(system, [])
    entries = []
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, "r", errors="ignore") as f:
            all_lines = f.readlines()
            entries.extend(all_lines[-lines:])
    return entries

def parse_and_store_logs():
    session = Session()

    system = platform.system().lower()
    if system == "windows":
        raw_lines = read_windows_event_logs()
    else:
        raw_lines = read_recent_logs()

    crashes_found = []
    warnings_found = []

    for line in raw_lines:
        line = line.strip()
        if not line:
            continue

        for pattern in CRASH_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                crashes_found.append(line)
                break

        for pattern in WARNING_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                warnings_found.append(line)
                entry = SyslogEntry(
                    timestamp=datetime.utcnow(),
                    source="eventlog" if system == "windows" else "syslog",
                    level="WARN",
                    message=line,
                    is_crash_precursor=1
                )
                session.add(entry)
                break

    session.commit()
    session.close()

    print(f"[log_collector] Found {len(crashes_found)} crashes, {len(warnings_found)} warnings")
    return crashes_found, warnings_found

if __name__ == "__main__":
    crashes, warnings = parse_and_store_logs()
    print("Crashes:", crashes)
    print("Warnings:", warnings)