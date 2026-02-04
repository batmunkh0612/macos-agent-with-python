"""
Nginx management plugin
"""

import subprocess
import logging

logger = logging.getLogger('Plugin.Nginx')

def handle(args):
    """
    Handle nginx commands
    
    Args:
        args: {
            "action": "restart" | "status" | "reload" | "test",
            "service": "nginx"  # optional
        }
    """
    action = args.get('action')
    service = args.get('service', 'nginx')
    
    logger.info(f"Nginx action: {action}")
    
    try:
        if action == 'restart':
            result = subprocess.run(
                ['systemctl', 'restart', service],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "action": "restart",
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr
            }
        
        elif action == 'status':
            result = subprocess.run(
                ['systemctl', 'status', service],
                capture_output=True,
                text=True,
                timeout=10
            )
            return {
                "action": "status",
                "running": result.returncode == 0,
                "output": result.stdout
            }
        
        elif action == 'reload':
            result = subprocess.run(
                ['systemctl', 'reload', service],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "action": "reload",
                "success": result.returncode == 0
            }
        
        elif action == 'test':
            result = subprocess.run(
                ['nginx', '-t'],
                capture_output=True,
                text=True,
                timeout=10
            )
            return {
                "action": "test",
                "valid": result.returncode == 0,
                "output": result.stdout + result.stderr
            }
        
        else:
            return {"error": f"Unknown action: {action}"}
            
    except subprocess.TimeoutExpired:
        return {"error": "Command timeout"}
    except Exception as e:
        return {"error": str(e)}
