#!/usr/bin/env python3
"""
System Plugin - System info and user management.
- System info: cpu, memory, disk, network (via args['info']).
- User management: create_user, delete_user, list_users, user_exists (via args['action']).
"""

import os
import platform
import logging
import subprocess
from datetime import datetime

import psutil

logger = logging.getLogger("Plugin.System")

SUDO_HINT = (
    " User management requires root. Either run the agent as root "
    "(e.g. sudo python agent.py) or configure passwordless sudo for sysadminctl."
)


def _is_root():
    """True if process has root privileges (no sudo needed)."""
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def _root_cmd(*args):
    """Prefix with sudo when not running as root."""
    return ([] if _is_root() else ["sudo"]) + list(args)


def handle(args):
    """
    Handle system commands.

    System info (args['info']): "all" | "cpu" | "memory" | "disk" | "network"
    User management (args['action']): create_user | delete_user | list_users | user_exists
    """
    action = args.get("action")
    if action == "create_user":
        return _create_user(args)
    if action == "delete_user":
        return _delete_user(args)
    if action == "list_users":
        return _list_users(args)
    if action == "user_exists":
        return _user_exists(args)
    if action is not None:
        return {
            "success": False,
            "error": f"Unknown action: {action}",
            "supported_actions": [
                "create_user",
                "delete_user",
                "list_users",
                "user_exists",
            ],
        }
    return _system_info(args)


def _system_info(args):
    """Get system information (cpu, memory, disk, network)."""
    info_type = args.get("info", "all")
    result = {}
    if info_type in ["all", "cpu"]:
        result["cpu"] = {
            "percent": psutil.cpu_percent(interval=1),
            "count": psutil.cpu_count(),
            "load_avg": os.getloadavg() if hasattr(os, "getloadavg") else None,
        }
    if info_type in ["all", "memory"]:
        mem = psutil.virtual_memory()
        result["memory"] = {
            "total": mem.total,
            "available": mem.available,
            "percent": mem.percent,
            "used": mem.used,
        }
    if info_type in ["all", "disk"]:
        disk = psutil.disk_usage("/")
        result["disk"] = {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        }
    if info_type in ["all", "network"]:
        net = psutil.net_io_counters()
        result["network"] = {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        }
    if info_type == "all":
        result["system"] = {
            "platform": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "hostname": platform.node(),
            "uptime": datetime.now().timestamp() - psutil.boot_time(),
        }
    return result


def _create_user(args):
    """Create a new user account (macOS sysadminctl)."""
    username = args.get("username")
    password = args.get("password")
    fullname = args.get("fullname", username)
    is_admin = args.get("admin", False)
    if not username:
        return {"success": False, "error": "Missing username"}
    logger.info("Creating user: %s", username)
    try:
        cmd = _root_cmd("sysadminctl", "-addUser", username, "-fullName", fullname)
        if password:
            cmd.extend(["-password", password])
        if is_admin:
            cmd.append("-admin")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info("User %s created successfully", username)
            return {
                "success": True,
                "message": f"User {username} created successfully",
                "username": username,
                "is_admin": is_admin,
                "stdout": result.stdout,
            }
        logger.error("Failed to create user %s: %s", username, result.stderr)
        err = result.stderr or ""
        hint = SUDO_HINT if ("password" in err or "terminal" in err) else ""
        return {
            "success": False,
            "error": f"Failed to create user: {result.stderr}{hint}",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
    except Exception as e:
        logger.error("Exception creating user: %s", e)
        return {"success": False, "error": str(e)}


def _delete_user(args):
    """Delete a user account (macOS sysadminctl with optional secure deletion)."""
    username = args.get("username")
    secure = args.get("secure", True)  # Delete home directory by default
    
    if not username:
        return {"success": False, "error": "Missing username"}
    
    logger.info("Deleting user: %s (secure=%s)", username, secure)
    
    try:
        # First check if user exists
        check_result = subprocess.run(
            ["dscl", ".", "-list", "/Users"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if username not in check_result.stdout.split("\n"):
            logger.warning("User %s does not exist", username)
            return {
                "success": False,
                "error": f"User {username} does not exist",
                "user_exists": False,
            }
        
        # Use sysadminctl to delete user (modern macOS method)
        # -deleteUser requires -secure flag to also delete home directory
        cmd = _root_cmd("sysadminctl", "-deleteUser", username)
        
        if secure:
            cmd.append("-secure")  # This will securely delete the home directory
        
        logger.info("Executing delete command: %s", " ".join(cmd))
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,  # Longer timeout for secure deletion
        )
        
        if result.returncode != 0:
            logger.error("Failed to delete user %s: %s", username, result.stderr)
            err = result.stderr or ""
            hint = SUDO_HINT if ("password" in err or "terminal" in err or "Authentication" in err) else ""
            return {
                "success": False,
                "error": f"Failed to delete user: {result.stderr}{hint}",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        
        # Verify deletion
        verify = subprocess.run(
            ["dscl", ".", "-list", "/Users"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        user_list = verify.stdout.split("\n")
        if username in user_list:
            logger.error("User %s still exists after deletion", username)
            return {
                "success": False,
                "error": f"User {username} still exists after deletion",
                "verification_failed": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        
        # Check if home directory still exists
        home_dir = f"/Users/{username}"
        home_exists = os.path.exists(home_dir)
        
        if secure and home_exists:
            logger.warning("Home directory still exists at %s, attempting manual cleanup", home_dir)
            # Fallback: manually remove home directory if sysadminctl didn't
            rm_result = subprocess.run(
                _root_cmd("rm", "-rf", home_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if rm_result.returncode != 0:
                logger.error("Failed to remove home directory: %s", rm_result.stderr)
                home_exists = os.path.exists(home_dir)
            else:
                home_exists = False
        
        logger.info("User %s deleted successfully", username)
        return {
            "success": True,
            "message": f"User {username} deleted successfully",
            "username": username,
            "secure_delete": secure,
            "home_directory_removed": not home_exists,
            "verified": True,
            "stdout": result.stdout,
        }
        
    except subprocess.TimeoutExpired:
        logger.error("Delete command timed out for user %s", username)
        return {"success": False, "error": "Command timed out"}
    except Exception as e:
        logger.error("Exception deleting user %s: %s", username, e)
        return {"success": False, "error": str(e)}


def _list_users(args):
    """List all user accounts (excluding system users)."""
    try:
        result = subprocess.run(
            ["dscl", ".", "-list", "/Users"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr}
        users = [
            line.strip()
            for line in result.stdout.strip().split("\n")
            if line.strip() and not line.strip().startswith("_")
        ]
        return {"success": True, "users": users, "count": len(users)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _user_exists(args):
    """Check if a user exists."""
    username = args.get("username")
    if not username:
        return {"success": False, "error": "Missing username"}
    try:
        result = subprocess.run(
            ["dscl", ".", "-list", "/Users"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr}
        exists = username in result.stdout.split("\n")
        return {"success": True, "username": username, "exists": exists}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("user_exists:", handle({"action": "user_exists", "username": "testuser"}))
    print("list_users:", handle({"action": "list_users"}))
    print("info all:", handle({"info": "all"}))