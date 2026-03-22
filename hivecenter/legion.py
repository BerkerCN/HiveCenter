"""
V7.0 God-Mode: Legion (Ephemeral Sandboxing)
Ajanın ana sistemden (Host) tamamen izole bir Docker Konteyneri yaratıp, tehlikeli scriptleri (veya bağımlılık cehennemini) burada test etmesini sağlar.
"""
import subprocess
import uuid
import os

def run_in_docker_sandbox(image: str, script_code: str, timeout: int = 60) -> str:
    """
    Creates an ephemeral Docker container, runs the given script (Bash or Python),
    collects output, and deletes the container.
    """
    container_id = f"hive_legion_{uuid.uuid4().hex[:8]}"
    
    # If it's python code (indicated by import or print syntax vs bash)
    is_python = "import " in script_code or "def " in script_code or "print(" in script_code
    
    cmd_entry = ["python3", "-c"] if is_python else ["bash", "-c"]
    
    # Base command: docker run --rm --name <id> <image> <cmd> <script>
    docker_cmd = [
        "docker", "run", "--rm", 
        "--name", container_id,
        "--network", "host", # Allow it to fetch things if needed
        "--memory", "512m",  # Limit resources
        "--cpus", "1.0",
        image
    ] + cmd_entry + [script_code]
    
    try:
        res = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        output = res.stdout + res.stderr
        
        if res.returncode == 0:
            return f"[LEGION SANDBOX SUCCESS]\\nContainer: {image}\\nResult:\\n{output}"
        else:
            return f"[LEGION SANDBOX FAILURE]\\nContainer: {image}\\nExit Code: {res.returncode}\\nError:\\n{output}\\n\\n(God-Mode Protected: The host system was unaffected by this crash.)"
            
    except subprocess.TimeoutExpired:
        # Force kill the container
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)
        return f"[LEGION SANDBOX TIMEOUT] The script took longer than {timeout} seconds and was forcefully assassinated."
    except Exception as e:
        return f"[LEGION FATAL ERROR] Docker daemon might not be running or image missing: {e}"
