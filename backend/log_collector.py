"""
log_collector.py — CrashSentinel
Reads system logs from Windows / Linux / macOS, detects crash and warning patterns,
and stores results in the database with deduplication and simulation flags.
"""

import os
import re
import platform
import subprocess
import logging
from datetime import datetime, timezone
from database import Session, SyslogEntry

# ── Logger setup ─────────────────────────────────────────────────────
# NOTE: basicConfig is intentionally NOT called here.
# main.py owns logging setup for the whole app.
# log_collector just gets its own named logger.
logger = logging.getLogger("log_collector")


# ── Flat log file paths (fallback for older Linux / macOS) ───────────
FLAT_LOG_PATHS = {
    "linux":  ["/var/log/syslog", "/var/log/kern.log", "/var/log/dmesg"],
    "darwin": ["/var/log/system.log"],
    "windows": []
}


# ── Patterns ─────────────────────────────────────────────────────────
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
    r"system crash",
    r"core dumped",
    r"killed process",
]

WARNING_PATTERNS = [
    r"(high|excessive) (memory|cpu|disk) (usage|pressure)",
    r"(temperature|thermal).*(critical|warning|throttling)",
    r"disk.*error",
    r"memory.*error",
    r"failed to allocate",
    r"soft lockup",
    r"hung_task",
    r"cpu.*throttl",
    r"i/o error",
    r"bad sector",
    r"swap.*full",
]


# ── Simulated logs (dev / fallback only) ─────────────────────────────
SIMULATED_LOGS = [
    "kernel: Out of memory: Killed process 1234 (chrome) total-vm:4096000kB",
    "WARNING: high memory usage detected on process explorer.exe",
    "disk error detected on drive C:",
    "thermal: temperature critical, throttling CPU",
    "fatal error in application crashtest.exe",
    "WARNING: failed to allocate memory block 512MB",
    "System: normal operation",
    "INFO: user logged in",
]

def simulate_logs() -> list:
    logger.warning("[log_collector]   Using SIMULATED logs — no real log source found")
    return SIMULATED_LOGS


# ── Per-OS readers ────────────────────────────────────────────────────

def read_windows_logs() -> tuple[list, bool]:
    """
    Returns (lines, is_simulated).
    Tries real Windows Event Logs first via pywin32.
    Falls back to simulated if pywin32 not installed.
    """
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
                        except Exception:
                            msg = str(event.StringInserts) if event.StringInserts else "No message"
                        timestamp = event.TimeGenerated.Format()
                        level = "ERROR" if event.EventType == win32con.EVENTLOG_ERROR_TYPE else "WARN"
                        entries.append(f"[{log_name}] [{level}] [{timestamp}] {msg}")
                        count += 1
            win32evtlog.CloseEventLog(hand)

        logger.info(f"[Windows] Read {len(entries)} real Event Log entries")
        return entries, False

    except ImportError:
        logger.warning("[Windows] pywin32 not installed — falling back to simulated logs")
        return simulate_logs(), True
    except Exception as e:
        logger.warning(f"[Windows] Event Log read failed: {e} — falling back to simulated logs")
        return simulate_logs(), True


def read_linux_logs() -> tuple[list, bool]:
    """
    Returns (lines, is_simulated).
    Tries journalctl first (modern systemd distros).
    Falls back to flat log files (/var/log/syslog etc.) for older distros.
    Falls back to simulated if nothing works.
    """
    # Try journalctl (Ubuntu 20+, Fedora, Arch, Debian 10+, etc.)
    try:
        result = subprocess.run(
            ["journalctl", "-n", "500", "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.splitlines()
            logger.info(f"[Linux] Read {len(lines)} lines from journalctl")
            return lines, False
    except FileNotFoundError:
        logger.info("[Linux] journalctl not found, trying flat log files...")
    except subprocess.TimeoutExpired:
        logger.warning("[Linux] journalctl timed out, trying flat log files...")
    except Exception as e:
        logger.warning(f"[Linux] journalctl failed: {e}")

    # Fallback: flat log files (older Ubuntu, Debian, CentOS)
    entries = []
    paths = FLAT_LOG_PATHS.get("linux", [])
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", errors="ignore") as f:
                lines = f.readlines()
                entries.extend(lines[-500:])
            logger.info(f"[Linux] Read {len(entries)} lines from {path}")
        except PermissionError:
            logger.warning(f"[Linux] Permission denied reading {path} — try running with sudo")

    if entries:
        return entries, False

    # Nothing worked
    logger.warning("[Linux] No log source found — falling back to simulated logs")
    return simulate_logs(), True


def read_macos_logs() -> tuple[list, bool]:
    """
    Returns (lines, is_simulated).
    Uses the macOS unified logging system via `log show` CLI.
    Falls back to /var/log/system.log for older macOS, then simulated.
    """
    # Modern macOS (10.12+) — unified logging
    try:
        result = subprocess.run(
            [
                "log", "show",
                "--last", "1h",
                "--predicate", "messageType == error OR messageType == fault",
                "--style", "syslog",
                "--info"
            ],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.splitlines()
            logger.info(f"[macOS] Read {len(lines)} lines from unified log")
            return lines, False
    except FileNotFoundError:
        logger.warning("[macOS] `log` command not found (pre-Sierra macOS?)")
    except subprocess.TimeoutExpired:
        logger.warning("[macOS] `log show` timed out — trying /var/log/system.log")
    except Exception as e:
        logger.warning(f"[macOS] log command failed: {e}")

    # Fallback: old /var/log/system.log (macOS < 10.12)
    fallback_path = "/var/log/system.log"
    if os.path.exists(fallback_path):
        try:
            with open(fallback_path, "r", errors="ignore") as f:
                lines = f.readlines()[-500:]
            logger.info(f"[macOS] Read {len(lines)} lines from {fallback_path}")
            return lines, False
        except PermissionError:
            logger.warning(f"[macOS] Permission denied reading {fallback_path}")

    logger.warning("[macOS] No log source found — falling back to simulated logs")
    return simulate_logs(), True


def get_system_logs() -> tuple[list, str, str, bool]:
    """
    Master dispatcher. Detects OS and calls the right reader.
    Returns (lines, os_name, source_label, is_simulated)
    """
    system = platform.system().lower()

    if system == "windows":
        lines, simulated = read_windows_logs()
        return lines, "windows", "windows-eventlog", simulated

    elif system == "linux":
        lines, simulated = read_linux_logs()
        source = "linux-simulated" if simulated else "linux-journald"
        return lines, "linux", source, simulated

    elif system == "darwin":
        lines, simulated = read_macos_logs()
        source = "darwin-simulated" if simulated else "darwin-unifiedlog"
        return lines, "darwin", source, simulated

    else:
        logger.warning(f"[log_collector] Unknown OS: {system} — using simulated logs")
        return simulate_logs(), system, "unknown-simulated", True


# ── Main parse + store ────────────────────────────────────────────────

def parse_and_store_logs() -> tuple[list, list]:
    """
    Reads logs for the current OS, pattern-matches for crashes and warnings,
    stores warnings to DB with deduplication, and returns crash lines.
    """
    session = Session()
    raw_lines, os_name, source_label, is_simulated = get_system_logs()

    if is_simulated:
        logger.warning("[log_collector]   Data source is SIMULATED — not real system logs")

    crashes_found = []
    warnings_found = []
    skipped_dupes = 0

    for line in raw_lines:
        line = line.strip()
        if not line:
            continue

        # Check crash patterns
        for pattern in CRASH_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                crashes_found.append(line)
                logger.info(f"[log_collector]  CRASH detected: {line[:80]}")
                break

        # Check warning patterns
        for pattern in WARNING_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):

                # ── Deduplication: skip if this exact message is already stored ──
                existing = session.query(SyslogEntry)\
                    .filter(SyslogEntry.message == line).first()
                if existing:
                    skipped_dupes += 1
                    break

                warnings_found.append(line)
                entry = SyslogEntry(
                    timestamp=datetime.now(timezone.utc),
                    source=source_label,
                    source_os=os_name,
                    level="WARN",
                    message=line,
                    is_crash_precursor=1,
                    is_simulated=1 if is_simulated else 0
                )
                session.add(entry)
                logger.info(f"[log_collector]  WARNING stored: {line[:80]}")
                break

    session.commit()
    session.close()

    logger.info(
        f"[log_collector] Scan complete — "
        f"{len(crashes_found)} crashes, {len(warnings_found)} new warnings, "
        f"{skipped_dupes} duplicates skipped | OS: {os_name} | simulated: {is_simulated}"
    )

    return crashes_found, warnings_found


# ── Dev runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Running log_collector manually...")
    crashes, warnings = parse_and_store_logs()
    print(f"\nCrashes found ({len(crashes)}):")
    for c in crashes:
        print(f"  {c}")
    print(f"\nWarnings found ({len(warnings)}):")
    for w in warnings:
        print(f"  {w}")