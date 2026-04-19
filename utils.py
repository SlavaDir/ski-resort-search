import subprocess
import threading
import os


_process_lock = threading.Lock()
_running_process = None

def run_subprocess(cmd):
  
    global _running_process
    with _process_lock:
     
        if _running_process and _running_process.poll() is None:
            yield "data: [Process already running]\n\n"
            return
        
 
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"


        _running_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8', 
            env=env,
            bufsize=1, 
        )
        
   
    for line in _running_process.stdout:
       
        yield f"data: {line.rstrip()}\n\n"
        
    
    _running_process.wait()
    yield f"data: [EXIT {_running_process.returncode}]\n\n"
    yield "data: __DONE__\n\n"
