import multiprocessing
import time
import signal
import sys

def cpu_stress_worker():
    """
    A worker function that performs continuous arithmetic 
    to consume CPU cycles.
    """
    # This prevents the process from printing a messy traceback when you press Ctrl+C
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    
    x = 0.0001
    while True:
        # Performing heavy floating-point operations
        x = x * 1.0000001
        if x > 1000.0:
            x = 0.0001

def main():
    # Detect the number of logical CPU cores available
    num_cores = multiprocessing.cpu_count()
    print(f"[+] Detecting {num_cores} CPU cores...")
    print(f"[+] Starting stress test on all cores. Press Ctrl+C to stop.")

    processes = []

    # Launch a worker process for each core
    for _ in range(num_cores):
        p = multiprocessing.Process(target=cpu_stress_worker)
        p.start()
        processes.append(p)

    try:
        # Keep the main script alive while workers run
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[-] Stopping the stress test...")
        # Terminate all worker processes safely
        for p in processes:
            p.terminate()
            p.join()
        print("[+] All tasks stopped. CPU usage should return to normal.")

if __name__ == "__main__":
    main()