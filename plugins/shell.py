"""
Shell command plugin - Execute shell scripts/commands on the agent
"""

import subprocess
import logging

logger = logging.getLogger("Plugin.Shell")


def handle(args: dict) -> dict:
    """
    Execute a shell script/command.

    Args:
        args: {
          "script": "echo hello",   # Required: command to execute
          "timeout": 30,            # Optional: timeout in seconds (default: 30)
          "cwd": "/tmp"             # Optional: working directory
        }
    
    Returns:
        dict with success, exit_code, stdout, stderr
    """
    script = args.get("script")
    timeout = args.get("timeout", 30)
    cwd = args.get("cwd")

    if not script:
        return {"success": False, "error": "Missing 'script' argument"}

    logger.info("Executing shell script: %s (timeout: %ss)", script, timeout)

    try:
        result = subprocess.run(
            script,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        
        output = {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout.strip() if result.stdout else "",
            "stderr": result.stderr.strip() if result.stderr else "",
        }
        
        logger.info("Script completed with exit code: %d", result.returncode)
        if result.stdout:
            logger.info("stdout: %s", result.stdout[:200])
        if result.stderr:
            logger.warning("stderr: %s", result.stderr[:200])
            
        return output
        
    except subprocess.TimeoutExpired:
        logger.error("Script timed out after %ss", timeout)
        return {"success": False, "error": f"Command timed out after {timeout}s"}
    except Exception as exc:
        logger.error("Script execution failed: %s", exc)
        return {"success": False, "error": str(exc)}

