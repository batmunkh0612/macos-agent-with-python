#!/usr/bin/env python3
"""
System Plugin - System info and user management.
- System info: cpu, memory, disk, network (via args['info']).
- User management: create_user, delete_user, list_users, user_exists (via args['action']).
  delete_user supports remove_secure_token (with password) and force_dscl_fallback so the
  account is removed from Users & Groups when sysadminctl leaves the DS record.
"""

import os
import platform
import logging
import subprocess
import time
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


def _secure_token_status(username):
    """Return True if user has Secure Token (can block full account deletion)."""
    try:
        r = subprocess.run(
            _root_cmd("sysadminctl", "-secureTokenStatus", username),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "ENABLED" in (r.stdout or "") or "ENABLED" in (r.stderr or "")
    except Exception:
        return False


def _delete_user(args):
    """Delete a user account (macOS sysadminctl with optional secure deletion).

    If the user has a Secure Token (Error -14120), pass remove_secure_token=True and
    password=<user's password>. When the agent runs as root (no Secure Token), also
    pass admin_user and admin_password for an admin that has Secure Token so we can
    run secureTokenOff. force_dscl_fallback removes the DS record if sysadminctl didn't.
    """
    username = args.get("username")
    secure = args.get("secure", True)  # Delete home directory by default
    user_password = args.get("password")  # Optional: for secureTokenOff
    remove_secure_token = args.get("remove_secure_token", False)
    force_dscl_fallback = args.get("force_dscl_fallback", True)  # Remove from DS if sysadminctl didn't

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

        # Remove Secure Token when requested so sysadminctl can fully delete the account.
        # Error -14120 means the target has Secure Token and the runner doesn't; use
        # admin_user + admin_password (an admin that has Secure Token) when agent runs as root.
        if remove_secure_token and user_password:
            admin_user = args.get("admin_user")
            admin_password = args.get("admin_password")
            logger.info("Removing Secure Token for user %s", username)
            tok_cmd = _root_cmd("sysadminctl", "-secureTokenOff", username, "-password", user_password)
            if admin_user and admin_password:
                tok_cmd.extend(["-adminUser", admin_user, "-adminPassword", admin_password])
            tok_off = subprocess.run(tok_cmd, capture_output=True, text=True, timeout=30)
            if tok_off.returncode != 0:
                logger.warning("Could not remove Secure Token: %s", tok_off.stderr or tok_off.stdout)
            else:
                logger.info("Secure Token removed for %s", username)
                time.sleep(1)

        # Use sysadminctl to delete user (modern macOS method)
        cmd = _root_cmd("sysadminctl", "-deleteUser", username)
        if secure:
            cmd.append("-secure")

        logger.info("Executing delete command: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        err = result.stderr or ""
        if result.returncode != 0 or "Error:-14120" in err or "-14120" in err:
            if "14120" in err:
                hint = (
                    " User has Secure Token; deletion failed (eDSPermissionError). Remove the token first: "
                    "call delete_user with remove_secure_token=true, password=<user's password>, and if the "
                    "agent runs as root, also pass admin_user and admin_password for an admin that has Secure Token."
                )
                return {
                    "success": False,
                    "error": f"Secure Token blocked deletion (Error -14120).{hint}",
                    "verification_failed": True,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                }
            critical_errors = ["Authentication failed", "Permission denied", "command not found", "Invalid user"]
            if result.returncode != 0 and any(e in err for e in critical_errors):
                hint = SUDO_HINT if ("password" in err or "terminal" in err or "Authentication" in err) else ""
                return {
                    "success": False,
                    "error": f"Failed to delete user: {result.stderr}{hint}",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                }

        stderr_lower = (result.stderr or "").lower()
        deletion_success_indicators = [
            "deleting record for",
            "securely removing",
            "killing all processes for uid",
        ]
        deletion_started = any(i in stderr_lower for i in deletion_success_indicators)

        if deletion_started:
            logger.info("Deletion command executed, waiting for directory service to update...")
            time.sleep(2)

        max_retries = 3
        retry_delay = 1
        user_still_exists = False

        for attempt in range(max_retries):
            verify = subprocess.run(
                ["dscl", ".", "-list", "/Users"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            user_list = [u.strip() for u in verify.stdout.split("\n") if u.strip()]
            user_still_exists = username in user_list
            if not user_still_exists:
                logger.info("User %s verified as deleted (attempt %d/%d)", username, attempt + 1, max_retries)
                break
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

        # If user still in Directory Service (still shows in Users & Groups), try dscl fallback
        if user_still_exists and force_dscl_fallback:
            logger.warning("User still in Directory Service after sysadminctl; removing record with dscl")
            dscl_remove = subprocess.run(
                _root_cmd("dscl", ".", "-delete", f"/Users/{username}"),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if dscl_remove.returncode == 0:
                time.sleep(1)
                final = subprocess.run(
                    ["dscl", ".", "-list", "/Users"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                user_still_exists = username in (final.stdout or "").split("\n")
            else:
                logger.warning("dscl fallback failed: %s", dscl_remove.stderr)

        if user_still_exists:
            hint = (
                " User may have Secure Token; try delete_user with remove_secure_token=True and password, "
                "or check System Preferences > Users & Groups."
            )
            return {
                "success": False,
                "error": f"User {username} still appears in Users & Groups.{hint}",
                "verification_failed": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        home_dir = f"/Users/{username}"
        home_exists = os.path.exists(home_dir)
        if secure and home_exists:
            logger.warning("Home directory still exists at %s, attempting manual cleanup", home_dir)
            rm_result = subprocess.run(
                _root_cmd("rm", "-rf", home_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if rm_result.returncode == 0:
                home_exists = False
            else:
                logger.error("Failed to remove home directory: %s", rm_result.stderr)

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