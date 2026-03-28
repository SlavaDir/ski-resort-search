import subprocess
import threading
import os

# These variables ensure only one AI process runs at a time
_process_lock = threading.Lock()
_running_process = None

def run_subprocess(cmd):
    """
    Runs a system command (like starting the AI script) and captures its output
    to send it directly to the web interface in real-time.
    """
    global _running_process
    with _process_lock:
        # Check if a process is already active
        if _running_process and _running_process.poll() is None:
            yield "data: [Process already running]\n\n"
            return
        
        # Set environment to UTF-8 to prevent text errors on Windows systems
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        # Start the external script as a child process
        _running_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8', 
            env=env,
            bufsize=1, # Line-buffered for immediate output
        )
        
    # Read the output line by line as the script works
    for line in _running_process.stdout:
        # Format the line for Server-Sent Events (SSE)
        yield f"data: {line.rstrip()}\n\n"
        
    # Wait for the script to finish and report the final status
    _running_process.wait()
    yield f"data: [EXIT {_running_process.returncode}]\n\n"
    yield "data: __DONE__\n\n"