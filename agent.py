#!/usr/bin/env python3
"""
Remote Agent - Self-updating agent with plugin system
"""

import os
import sys
import time
import json
import hashlib
import socket
import logging
import threading
import importlib.util
from typing import Dict, Any, Optional
from datetime import datetime

import websocket
import requests
import yaml

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('Agent')

# =============================================================================
# VERSION INFO - Update this when releasing new versions
# =============================================================================
VERSION = "2.1.0"
RELEASE_DATE = "2026-02-04"
RELEASE_NOTES = "Serial number as unique agent ID, auto-detection support"
# =============================================================================

# Paths - use absolute paths based on script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.yaml")
PLUGINS_DIR = os.path.join(SCRIPT_DIR, "plugins")
AGENT_FILE = os.path.join(SCRIPT_DIR, "agent.py")


def get_machine_id() -> str:
    """
    Get unique machine identifier.
    - macOS: Uses hardware serial number (unique per device)
    - Linux: Uses machine-id or generates from hardware info
    - Fallback: hostname
    """
    import subprocess
    
    try:
        if sys.platform == 'darwin':
            # macOS - get hardware serial number
            result = subprocess.run(
                ['ioreg', '-l'],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.split('\n'):
                if 'IOPlatformSerialNumber' in line:
                    # Extract serial: "IOPlatformSerialNumber" = "XXXXXXXXXX"
                    serial = line.split('"')[-2]
                    if serial and len(serial) > 5:
                        return f"mac-{serial.lower()}"
            
            # Fallback: try system_profiler
            result = subprocess.run(
                ['system_profiler', 'SPHardwareDataType'],
                capture_output=True,
                text=True,
                timeout=10
            )
            for line in result.stdout.split('\n'):
                if 'Serial Number' in line:
                    serial = line.split(':')[-1].strip()
                    if serial:
                        return f"mac-{serial.lower()}"
        
        elif sys.platform == 'linux':
            # Linux - try machine-id first
            machine_id_files = [
                '/etc/machine-id',
                '/var/lib/dbus/machine-id'
            ]
            for path in machine_id_files:
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        machine_id = f.read().strip()[:12]
                        return f"linux-{machine_id}"
            
            # Fallback: try DMI serial
            result = subprocess.run(
                ['sudo', 'dmidecode', '-s', 'system-serial-number'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return f"linux-{result.stdout.strip().lower()}"
    
    except Exception as e:
        logger.warning(f"Could not get machine ID: {e}")
    
    # Final fallback: hostname
    return socket.gethostname().lower().replace(' ', '-')

class AgentConfig:
    """Configuration manager"""
    
    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self) -> dict:
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_file}")
            return self.default_config()
    
    def default_config(self) -> dict:
        """Default configuration"""
        return {
            'server': {
                'ws_url': 'wss://your-worker.workers.dev/ws',
                'graphql_url': 'https://your-worker.workers.dev/graphql',
            },
            'agent': {
                'id': get_machine_id(),  # Uses serial number on macOS
                'heartbeat_interval': 30,
                'poll_interval': 60,
            },
            'plugins': {
                'auto_sync': True,
                'sync_interval': 300,  # 5 minutes
            }
        }
    
    def get(self, key: str, default=None):
        """Get config value by dot notation (e.g., 'server.ws_url')"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        
        return value if value is not None else default


class PluginManager:
    """Plugin loader and manager"""
    
    def __init__(self, plugins_dir: str = PLUGINS_DIR):
        self.plugins_dir = plugins_dir
        self.plugins: Dict[str, Any] = {}
        
        logger.info(f"Plugin directory: {self.plugins_dir}")
        
        # Create plugins directory
        os.makedirs(plugins_dir, exist_ok=True)

        # Auto-load any local plugins on startup (shell, system, nginx, etc.)
        self.load_local_plugins()

    def load_local_plugins(self) -> None:
        """Load all local *.py plugins from the plugins directory."""
        logger.info(f"Loading local plugins from: {self.plugins_dir}")
        
        if not os.path.exists(self.plugins_dir):
            logger.warning(f"Plugins directory does not exist: {self.plugins_dir}")
            return
            
        try:
            files = os.listdir(self.plugins_dir)
            logger.info(f"Found files in plugins dir: {files}")
            
            for filename in files:
                if not filename.endswith(".py") or filename == "__init__.py":
                    continue

                name = filename[:-3]
                module_name = f"plugin_local_{name}"
                plugin_path = os.path.join(self.plugins_dir, filename)

                logger.info(f"Loading plugin: {name} from {plugin_path}")

                try:
                    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
                    if spec is None or spec.loader is None:
                        logger.error("Could not load spec for plugin %s", name)
                        continue

                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)  # type: ignore[union-attr]

                    if not hasattr(module, "handle"):
                        logger.error("Local plugin %s missing 'handle' function", name)
                        continue

                    self.plugins[name] = module
                    logger.info("✅ Local plugin loaded: %s", name)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to load local plugin %s: %s", name, exc)
                    
            logger.info(f"Total plugins loaded: {list(self.plugins.keys())}")
        except FileNotFoundError as e:
            logger.error(f"Plugin directory not found: {e}")
        except Exception as e:
            logger.error(f"Error loading plugins: {e}")
    
    def load_plugin(self, name: str, code: str, checksum: str) -> bool:
        """Load plugin from code string"""
        try:
            # Verify checksum
            actual_checksum = hashlib.sha256(code.encode()).hexdigest()
            if actual_checksum != checksum:
                logger.error(f"Plugin {name} checksum mismatch!")
                return False
            
            # Create module
            module_name = f"plugin_{name}"
            spec = importlib.util.spec_from_loader(module_name, loader=None)
            module = importlib.util.module_from_spec(spec)
            
            # Execute code
            exec(code, module.__dict__)
            
            # Verify plugin has required methods
            if not hasattr(module, 'handle'):
                logger.error(f"Plugin {name} missing 'handle' function")
                return False
            
            # Store plugin
            self.plugins[name] = module
            logger.info(f"✅ Plugin loaded: {name}")
            
            # Save to disk for persistence
            plugin_file = os.path.join(self.plugins_dir, f"{name}.py")
            with open(plugin_file, 'w') as f:
                f.write(code)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load plugin {name}: {e}")
            return False
    
    def execute_plugin(self, name: str, args: dict) -> dict:
        """Execute plugin command"""
        logger.info(f"Executing plugin: {name} with args: {args}")
        logger.info(f"Available plugins: {list(self.plugins.keys())}")
        
        plugin = self.plugins.get(name)
        
        if not plugin:
            error_msg = f"Plugin '{name}' not found. Available: {list(self.plugins.keys())}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        
        try:
            result = plugin.handle(args)
            logger.info(f"Plugin {name} result: {result}")
            
            # Ensure result has success field
            if isinstance(result, dict):
                if 'success' not in result:
                    result['success'] = True
                return result
            
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            logger.error(f"Plugin {name} execution failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def list_plugins(self) -> list:
        """List loaded plugins"""
        return list(self.plugins.keys())


class GraphQLClient:
    """GraphQL API client"""
    
    def __init__(self, url: str):
        self.url = url
    
    def query(self, query_str: str, variables: Optional[dict] = None) -> dict:
        """Execute GraphQL query"""
        try:
            response = requests.post(
                self.url,
                json={
                    "query": query_str,
                    "variables": variables or {}
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"GraphQL request failed: {e}")
            return {"errors": [{"message": str(e)}]}
    
    def get_pending_commands(self, agent_id: str, limit: int = 10) -> list:
        """Get pending commands for agent"""
        query = """
        query GetCommands($agentId: String!, $limit: Int) {
          getPendingCommands(agentId: $agentId, limit: $limit) {
            id
            command
            priority
          }
        }
        """
        result = self.query(query, {"agentId": agent_id, "limit": limit})
        
        if "errors" in result:
            return []
        
        return result.get("data", {}).get("getPendingCommands", [])
    
    def update_command_status(self, cmd_id: int, status: str, result: dict = None):
        """Update command status"""
        mutation = """
        mutation UpdateStatus($id: Int!, $status: String!, $result: JSON) {
          updateCommandStatus(id: $id, status: $status, result: $result) {
            id
          }
        }
        """
        self.query(mutation, {
            "id": cmd_id,
            "status": status,
            "result": result
        })
    
    def report_heartbeat(self, agent_id: str, version: str, status: str = "online"):
        """Send heartbeat"""
        mutation = """
        mutation Heartbeat(
          $agentId: String!
          $version: String
          $status: String
          $ipAddress: String
          $hostname: String
        ) {
          reportHeartbeat(
            agentId: $agentId
            version: $version
            status: $status
            ipAddress: $ipAddress
            hostname: $hostname
          )
        }
        """
        
        # Get IP address
        try:
            ip = requests.get('https://api.ipify.org', timeout=5).text
        except:
            ip = None
        
        self.query(mutation, {
            "agentId": agent_id,
            "version": version,
            "status": status,
            "ipAddress": ip,
            "hostname": socket.gethostname()
        })
    
    def sync_plugins(self) -> list:
        """Get all plugins from server"""
        query = """
        query GetPlugins {
          getPlugins {
            name
            version
            code
            checksum
          }
        }
        """
        result = self.query(query)
        
        if "errors" in result:
            return []
        
        return result.get("data", {}).get("getPlugins", [])
    
    def get_agent_update(self) -> Optional[dict]:
        """Check for agent updates from server"""
        query = """
        query GetAgentUpdate($currentVersion: String!) {
          getAgentUpdate(currentVersion: $currentVersion) {
            version
            code
            checksum
            releaseNotes
          }
        }
        """
        result = self.query(query, {"currentVersion": VERSION})
        
        if "errors" in result:
            return None
        
        return result.get("data", {}).get("getAgentUpdate")


class Agent:
    """Main Agent class"""
    
    def __init__(self, config_file: str = CONFIG_FILE):
        self.config = AgentConfig(config_file)
        
        # Get agent ID - use serial number if "auto" or empty
        configured_id = self.config.get('agent.id')
        if not configured_id or configured_id.lower() == 'auto':
            self.agent_id = get_machine_id()
            logger.info(f"Auto-detected machine ID: {self.agent_id}")
        else:
            self.agent_id = configured_id
        
        self.version = VERSION
        
        # Components
        self.graphql = GraphQLClient(self.config.get('server.graphql_url'))
        self.plugin_manager = PluginManager()
        
        # WebSocket
        self.ws = None
        self.ws_connected = False
        
        # State
        self.running = True
        
        logger.info("=" * 60)
        logger.info(f"🤖 Agent v{self.version} initialized")
        logger.info(f"   Agent ID: {self.agent_id}")
        logger.info(f"   Release: {RELEASE_DATE}")
        logger.info(f"   Notes: {RELEASE_NOTES}")
        logger.info("=" * 60)
    
    def sync_plugins(self):
        """Sync plugins from server"""
        logger.info("Syncing plugins from server...")
        
        plugins = self.graphql.sync_plugins()
        
        if plugins:
            logger.info(f"Server returned {len(plugins)} plugin(s)")
            for plugin in plugins:
                self.plugin_manager.load_plugin(
                    plugin['name'],
                    plugin['code'],
                    plugin['checksum']
                )
        else:
            logger.info("No plugins from server (using local plugins only)")
        
        logger.info(f"All available plugins: {self.plugin_manager.list_plugins()}")
    
    def self_update(self, update_url: str = None, force: bool = False) -> dict:
        """
        Self-update the agent from server or URL.
        
        Args:
            update_url: Optional direct URL to download agent.py from
            force: Force update even if version is the same
        
        Returns:
            dict with success status and message
        """
        import subprocess
        
        logger.info("=" * 60)
        logger.info("🔄 SELF-UPDATE PROCESS STARTED")
        logger.info(f"   Current Version: {self.version}")
        logger.info(f"   Release Date: {RELEASE_DATE}")
        logger.info("=" * 60)
        
        try:
            new_code = None
            new_version = None
            checksum = None
            
            # Method 1: Update from direct URL
            if update_url:
                logger.info(f"📥 Downloading from URL: {update_url}")
                response = requests.get(update_url, timeout=30)
                response.raise_for_status()
                new_code = response.text
                logger.info(f"   Downloaded {len(new_code)} bytes")
                
                # Extract version from downloaded code
                new_version = "unknown"
                for line in new_code.split('\n'):
                    if line.strip().startswith('VERSION = '):
                        new_version = line.split('"')[1]
                        break
                
                checksum = hashlib.sha256(new_code.encode()).hexdigest()
                logger.info(f"   Detected version: {new_version}")
                logger.info(f"   Checksum: {checksum[:16]}...")
            
            # Method 2: Update from GraphQL server
            else:
                logger.info("📡 Checking server for updates...")
                update_info = self.graphql.get_agent_update()
                
                if not update_info:
                    logger.info("✓ No update available from server")
                    return {
                        "success": True,
                        "message": "No update available",
                        "current_version": self.version
                    }
                
                new_version = update_info.get('version')
                new_code = update_info.get('code')
                checksum = update_info.get('checksum')
                
                logger.info(f"   Server version: {new_version}")
                
                # Check if we need to update
                if new_version == self.version and not force:
                    logger.info(f"✓ Already at latest version {self.version}")
                    return {
                        "success": True,
                        "message": f"Already at latest version {self.version}",
                        "current_version": self.version
                    }
            
            if not new_code:
                logger.error("❌ No update code received")
                return {"success": False, "error": "No update code received"}
            
            # Verify checksum if provided
            if checksum:
                actual_checksum = hashlib.sha256(new_code.encode()).hexdigest()
                if actual_checksum != checksum:
                    logger.error("❌ Checksum mismatch - update rejected!")
                    logger.error(f"   Expected: {checksum[:16]}...")
                    logger.error(f"   Got:      {actual_checksum[:16]}...")
                    return {
                        "success": False,
                        "error": "Checksum mismatch - update rejected"
                    }
                logger.info("✓ Checksum verified")
            
            # Backup current agent
            backup_file = f"{AGENT_FILE}.backup"
            logger.info(f"💾 Creating backup: {backup_file}")
            
            with open(AGENT_FILE, 'r') as f:
                current_code = f.read()
            with open(backup_file, 'w') as f:
                f.write(current_code)
            logger.info("   Backup created successfully")
            
            # Write new code
            logger.info(f"📝 Writing new agent code to: {AGENT_FILE}")
            with open(AGENT_FILE, 'w') as f:
                f.write(new_code)
            logger.info("   New code written successfully")
            
            logger.info("=" * 60)
            logger.info("✅ UPDATE SUCCESSFUL!")
            logger.info(f"   Old Version: {self.version}")
            logger.info(f"   New Version: {new_version}")
            logger.info("=" * 60)
            logger.info("🔄 Scheduling agent restart in 2 seconds...")
            
            # Schedule restart (runs after we return the result)
            def restart_service():
                time.sleep(2)  # Wait for response to be sent
                logger.info("🔄 Executing restart...")
                
                if sys.platform == 'darwin':
                    # macOS - use launchctl
                    plist = os.path.expanduser(
                        '~/Library/LaunchAgents/com.remote-agent.plist'
                    )
                    logger.info(f"   Unloading: {plist}")
                    subprocess.run(['launchctl', 'unload', plist], check=False)
                    logger.info(f"   Loading: {plist}")
                    subprocess.run(['launchctl', 'load', plist], check=False)
                else:
                    # Linux - use systemctl
                    logger.info("   Restarting systemd service...")
                    subprocess.run(
                        ['sudo', 'systemctl', 'restart', 'remote-agent'],
                        check=False
                    )
            
            threading.Thread(target=restart_service, daemon=True).start()
            
            return {
                "success": True,
                "message": f"Updated from {self.version} to {new_version}",
                "old_version": self.version,
                "new_version": new_version,
                "restarting": True
            }
            
        except Exception as e:
            logger.error(f"Self-update failed: {e}")
            return {"success": False, "error": str(e)}
    
    def update_plugin_from_url(self, name: str, url: str) -> dict:
        """
        Update a plugin from a URL.
        
        Args:
            name: Plugin name
            url: URL to download plugin code from
        
        Returns:
            dict with success status
        """
        try:
            logger.info(f"Downloading plugin {name} from: {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            code = response.text
            checksum = hashlib.sha256(code.encode()).hexdigest()
            
            success = self.plugin_manager.load_plugin(name, code, checksum)
            
            if success:
                return {
                    "success": True,
                    "message": f"Plugin {name} updated successfully",
                    "plugins": self.plugin_manager.list_plugins()
                }
            else:
                return {"success": False, "error": f"Failed to load plugin {name}"}
                
        except Exception as e:
            logger.error(f"Plugin update failed: {e}")
            return {"success": False, "error": str(e)}
    
    def execute_command(self, cmd: dict):
        """Execute a command"""
        cmd_id = cmd['id']
        command = cmd['command']

        # Support backends that store JSON as string
        if isinstance(command, str):
            try:
                command = json.loads(command)
            except Exception as exc:  # noqa: BLE001
                logger.error("Command %s has invalid JSON payload: %s", cmd_id, exc)
                self.graphql.update_command_status(cmd_id, 'failed', {
                    "error": f"Invalid command JSON: {exc}"
                })
                return

        cmd_type = command.get('type')
        
        logger.info(f"Executing command {cmd_id}: {cmd_type}")
        
        # Update status to processing
        self.graphql.update_command_status(cmd_id, 'processing')
        
        try:
            result = None
            
            # Built-in commands
            if cmd_type == 'ping':
                result = {"message": "pong", "timestamp": datetime.now().isoformat()}
            
            elif cmd_type == 'sync_plugins':
                self.sync_plugins()
                result = {"success": True, "plugins": self.plugin_manager.list_plugins()}
            
            elif cmd_type == 'reload_plugins':
                # Reload local plugins
                self.plugin_manager.load_local_plugins()
                result = {"success": True, "plugins": self.plugin_manager.list_plugins()}
            
            elif cmd_type == 'list_plugins':
                result = {"success": True, "plugins": self.plugin_manager.list_plugins()}
            
            elif cmd_type == 'get_status':
                # Determine if ID was auto-detected or configured
                configured_id = self.config.get('agent.id')
                id_source = "auto-detected (serial)" if not configured_id or configured_id.lower() == 'auto' else "configured"
                
                result = {
                    "success": True,
                    "agent_id": self.agent_id,
                    "id_source": id_source,
                    "version": self.version,
                    "release_date": RELEASE_DATE,
                    "release_notes": RELEASE_NOTES,
                    "uptime": time.time(),
                    "plugins": self.plugin_manager.list_plugins(),
                    "ws_connected": self.ws_connected,
                    "platform": sys.platform
                }
            
            # Self-update commands
            elif cmd_type == 'self_update':
                update_url = command.get('url')  # Optional direct URL
                force = command.get('force', False)
                result = self.self_update(update_url=update_url, force=force)
            
            elif cmd_type == 'check_update':
                update_info = self.graphql.get_agent_update()
                if update_info:
                    result = {
                        "success": True,
                        "update_available": True,
                        "current_version": self.version,
                        "new_version": update_info.get('version'),
                        "release_notes": update_info.get('releaseNotes')
                    }
                else:
                    result = {
                        "success": True,
                        "update_available": False,
                        "current_version": self.version
                    }
            
            elif cmd_type == 'update_plugin':
                plugin_name = command.get('name')
                plugin_url = command.get('url')
                if not plugin_name or not plugin_url:
                    result = {
                        "success": False,
                        "error": "Missing 'name' or 'url' in command"
                    }
                else:
                    result = self.update_plugin_from_url(plugin_name, plugin_url)
            
            elif cmd_type == 'restart':
                result = {"success": True, "message": "Agent restarting..."}
                # Schedule restart
                def do_restart():
                    time.sleep(2)
                    if sys.platform == 'darwin':
                        import subprocess
                        plist = os.path.expanduser(
                            '~/Library/LaunchAgents/com.remote-agent.plist'
                        )
                        subprocess.run(['launchctl', 'unload', plist], check=False)
                        subprocess.run(['launchctl', 'load', plist], check=False)
                    else:
                        import subprocess
                        subprocess.run(
                            ['sudo', 'systemctl', 'restart', 'remote-agent'],
                            check=False
                        )
                threading.Thread(target=do_restart, daemon=True).start()
            
            # Plugin commands
            elif cmd_type == 'plugin_command':
                plugin_name = command.get('plugin')
                args = command.get('args', {})
                
                if not plugin_name:
                    result = {"success": False, "error": "Missing 'plugin' field in command"}
                else:
                    result = self.plugin_manager.execute_plugin(plugin_name, args)
            
            else:
                result = {"error": f"Unknown command type: {cmd_type}"}
            
            # Update status to done
            status = 'done' if result.get('success', True) else 'failed'
            self.graphql.update_command_status(cmd_id, status, result)
            
            logger.info(f"Command {cmd_id} completed: {status}")
            
        except Exception as e:
            logger.error(f"Command {cmd_id} failed: {e}")
            self.graphql.update_command_status(cmd_id, 'failed', {
                "error": str(e)
            })
    
    def poll_commands(self):
        """Poll for pending commands (fallback when WebSocket is down)"""
        commands = self.graphql.get_pending_commands(self.agent_id)
        
        for cmd in commands:
            self.execute_command(cmd)
    
    def heartbeat_loop(self):
        """Send periodic heartbeat"""
        interval = self.config.get('agent.heartbeat_interval', 30)
        
        while self.running:
            try:
                self.graphql.report_heartbeat(
                    self.agent_id,
                    self.version,
                    'online' if self.ws_connected else 'polling'
                )
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
            
            time.sleep(interval)
    
    def polling_loop(self):
        """Fallback polling loop"""
        interval = self.config.get('agent.poll_interval', 60)
        
        while self.running:
            if not self.ws_connected:
                try:
                    self.poll_commands()
                except Exception as e:
                    logger.error(f"Polling failed: {e}")
            
            time.sleep(interval)
    
    def plugin_sync_loop(self):
        """Periodic plugin sync"""
        if not self.config.get('plugins.auto_sync', True):
            return
        
        interval = self.config.get('plugins.sync_interval', 300)
        
        while self.running:
            time.sleep(interval)
            
            try:
                self.sync_plugins()
            except Exception as e:
                logger.error(f"Plugin sync failed: {e}")
    
    def auto_update_loop(self):
        """Automatic update check loop"""
        if not self.config.get('updates.auto_update', False):
            logger.info("Auto-update is disabled")
            return
        
        interval = self.config.get('updates.check_interval', 3600)  # Default 1 hour
        update_url = self.config.get('updates.update_url', '')
        
        logger.info(f"Auto-update enabled, checking every {interval}s")
        
        while self.running:
            time.sleep(interval)
            
            try:
                logger.info("🔍 Checking for updates...")
                
                if update_url:
                    # Check if URL has newer version (by downloading and comparing)
                    result = self.self_update(update_url=update_url)
                else:
                    # Check server for updates
                    update_info = self.graphql.get_agent_update()
                    
                    if update_info and update_info.get('version') != self.version:
                        logger.info(
                            f"Update available: {self.version} -> "
                            f"{update_info.get('version')}"
                        )
                        result = self.self_update()
                    else:
                        logger.info(f"No updates available (current: {self.version})")
                        continue
                
                if result.get('success') and result.get('restarting'):
                    logger.info("Update applied, agent will restart...")
                    break  # Exit loop as agent is restarting
                    
            except Exception as e:
                logger.error(f"Auto-update check failed: {e}")
    
    def on_ws_message(self, ws, message):
        """WebSocket message handler"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'new_command':
                # New command received via WebSocket
                cmd = data.get('command')
                self.execute_command(cmd)
            
            elif msg_type == 'sync_plugins':
                # Plugin update notification
                self.sync_plugins()
            
            elif msg_type == 'ping':
                # Server ping
                ws.send(json.dumps({"type": "pong"}))
                
        except Exception as e:
            logger.error(f"WebSocket message error: {e}")
    
    def on_ws_error(self, ws, error):
        """WebSocket error handler"""
        logger.error(f"WebSocket error: {error}")
        self.ws_connected = False
    
    def on_ws_close(self, ws, close_status_code, close_msg):
        """WebSocket close handler"""
        logger.warning(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.ws_connected = False
        
        # Reconnect after delay
        time.sleep(5)
        if self.running:
            self.start_websocket()
    
    def on_ws_open(self, ws):
        """WebSocket open handler"""
        logger.info("✅ WebSocket connected")
        self.ws_connected = True
        
        # Check for missed commands
        try:
            self.poll_commands()
        except Exception as e:
            logger.error(f"Failed to check missed commands: {e}")
    
    def start_websocket(self):
        """Start WebSocket connection"""
        ws_url = self.config.get('server.ws_url')
        url = f"{ws_url}?agentId={self.agent_id}"
        
        logger.info(f"Connecting to WebSocket: {url}")
        
        self.ws = websocket.WebSocketApp(
            url,
            on_message=self.on_ws_message,
            on_error=self.on_ws_error,
            on_close=self.on_ws_close,
            on_open=self.on_ws_open
        )
        
        # Run in thread
        ws_thread = threading.Thread(
            target=self.ws.run_forever,
            daemon=True
        )
        ws_thread.start()
    
    def start(self):
        """Start agent"""
        logger.info("🚀 Starting agent...")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"Script directory: {SCRIPT_DIR}")
        logger.info(f"Plugins directory: {PLUGINS_DIR}")
        logger.info(f"Local plugins at startup: {self.plugin_manager.list_plugins()}")
        
        # Initial plugin sync from server
        try:
            self.sync_plugins()
        except Exception as e:
            logger.error(f"Initial plugin sync failed: {e}")
        
        # Start background threads
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()
        threading.Thread(target=self.polling_loop, daemon=True).start()
        threading.Thread(target=self.plugin_sync_loop, daemon=True).start()
        threading.Thread(target=self.auto_update_loop, daemon=True).start()
        
        # Start WebSocket
        self.start_websocket()
        
        # Main loop
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
            if self.ws:
                self.ws.close()


def main():
    """Main entry point"""
    agent = Agent()
    agent.start()


if __name__ == "__main__":
    main()
