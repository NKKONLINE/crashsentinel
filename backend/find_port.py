"""
Run this on your Windows machine to find a free port CrashSentinel can use.
Usage: python find_port.py
"""
import socket

ports_to_try = [8001, 8080, 8888, 5000, 3001, 4000, 9000, 7000, 6000, 1337]

for port in ports_to_try:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', port))
        s.close()
        print(f"  [OK]  Port {port} is available — use this one!")
    except OSError as e:
        print(f"  [BLOCKED] Port {port}: {e}")