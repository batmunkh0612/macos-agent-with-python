#!/usr/bin/env python3
"""
Remote Agent v1.0.0 - OLD VERSION (for testing self-update)

This is an older version of the agent that can be updated to the latest version.
Install this first, then trigger a self_update command to see the update process.
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
import subprocess
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
# VERSION INFO - This is the OLD version that will be updated
# =============================================================================
VERSION = "1.0.0"
RELEASE_DATE = "2025-01-01"
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.yaml")
PLUGINS_DIR = os.path.join(SCRIPT_DIR, "plugins")
AGENT_FILE = os.path.join(SCRIPT_DIR, "agent.py")


class AgentConfig:
    """Configuration manager"""
    
    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self) -> dict:
        try:
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_file}")
            return self.default_config()
    
    def default_config(self) -> dict:
        return {
            'server': {
                'ws_url': 'wss://your-worker.workers.dev/ws',
                'graphql_url': 'https://your-worker.workers.dev/graphql',
            },
            'agent': {
                'id': socket.gethostname(),
                'heartbeat_interval': 30,
                'poll_interval': 60,
            },
            'plugins': {
                'auto_sync': True,
                'sync_interval': 300,
            }
        }
    
    def get(self, key: str, default=None):
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
        os.makedirs(plugins_dir, exist_ok=True)
        self.load_local_plugins()

    def load_local_plugins(self) -> None:
        logger.info(f"Loading plugins from: {self.plugins_dir}")
        if not os.path.exists(self.plugins_dir):
            return
        try:
            for filename in os.listdir(self.plugins_dir):
                if not filename.endswith(".py") or filename == "__init__.py":
                    continue
                name = filename[:-3]
                plugin_path = os.path.join(self.plugins_dir, filename)
                try:
                    spec = importlib.util.spec_from_file_location(f"plugin_{name}", plugin_path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        if hasattr(module, "handle"):
                            self.plugins[name] = module
                            logger.info(f"✅ Plugin loaded: {name}")
                except Exception as e:
                    logger.error(f"Failed to load plugin {name}: {e}")
        except Exception as e:
            logger.error(f"Error loading plugins: {e}")
    
    def load_plugin(self, name: str, code: str, checksum: str) -> bool:
        try:
            actual_checksum = hashlib.sha256(code.encode()).hexdigest()
            if actual_checksum != checksum:
                logger.error(f"Plugin {name} checksum mismatch!")
                return False
            spec = importlib.util.spec_from_loader(f"plugin_{name}", loader=None)
            module = importlib.util.module_from_spec(spec)
            exec(code, module.__dict__)
            if not hasattr(module, 'handle'):
                return False
            self.plugins[name] = module
            plugin_file = os.path.join(self.plugins_dir, f"{name}.py")
            with open(plugin_file, 'w') as f:
                f.write(code)
            return True
        except Exception as e:
            logger.error(f"Failed to load plugin {name}: {e}")
            return False
    
    def execute_plugin(self, name: str, args: dict) -> dict:
        plugin = self.plugins.get(name)
        if not plugin:
            return {"success": False, "error": f"Plugin '{name}' not found"}
        try:
            result = plugin.handle(args)
            if isinstance(result, dict) and 'success' not in result:
                result['success'] = True
            return result if isinstance(result, dict) else {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def list_plugins(self) -> list:
        return list(self.plugins.keys())


class GraphQLClient:
    """GraphQL API client"""
    
    def __init__(self, url: str):
        self.url = url
    
    def query(self, query_str: str, variables: Optional[dict] = None) -> dict:
        try:
            response = requests.post(
                self.url,
                json={"query": query_str, "variables": variables or {}},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"GraphQL request failed: {e}")
            return {"errors": [{"message": str(e)}]}
    
    def get_pending_commands(self, agent_id: str, limit: int = 10) -> list:
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
        mutation = """
        mutation UpdateStatus($id: Int!, $status: String!, $result: JSON) {
          updateCommandStatus(id: $id, status: $status, result: $result) { id }
        }
        """
        self.query(mutation, {"id": cmd_id, "status": status, "result": result})
    
    def report_heartbeat(self, agent_id: str, version: str, status: str = "online"):
        mutation = """
        mutation Heartbeat($agentId: String!, $version: String, $status: String, $ipAddress: String, $hostname: String) {
          reportHeartbeat(agentId: $agentId, version: $version, status: $status, ipAddress: $ipAddress, hostname: $hostname)
        }
        """
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
        query = """
        query GetPlugins {
          getPlugins { name version code checksum }
        }
        """
        result = self.query(query)
        if "errors" in result:
            return []
        return result.get("data", {}).get("getPlugins", [])


class Agent:
    """Main Agent class - v1.0.0"""
    
    def __init__(self, config_file: str = CONFIG_FILE):
        self.config = AgentConfig(config_file)
        self.agent_id = self.config.get('agent.id')
        self.version = VERSION
        self.graphql = GraphQLClient(self.config.get('server.graphql_url'))
        self.plugin_manager = PluginManager()
        self.ws = None
        self.ws_connected = False
        self.running = True
        
        logger.info("=" * 60)
        logger.info(f"🤖 Agent v{self.version} initialized")
        logger.info(f"   Agent ID: {self.agent_id}")
        logger.info(f"   Release: {RELEASE_DATE}")
        logger.info("=" * 60)
    
    def sync_plugins(self):
        logger.info("Syncing plugins...")
        plugins = self.graphql.sync_plugins()
        for plugin in plugins:
            self.plugin_manager.load_plugin(plugin['name'], plugin['code'], plugin['checksum'])
        logger.info(f"Plugins: {self.plugin_manager.list_plugins()}")
    
    def self_update(self, update_url: str = None) -> dict:
        """Self-update the agent from a URL"""
        logger.info("=" * 60)
        logger.info("🔄 SELF-UPDATE STARTED")
        logger.info(f"   Current version: {self.version}")
        logger.info("=" * 60)
        
        try:
            if not update_url:
                return {"success": False, "error": "No update URL provided"}
            
            logger.info(f"📥 Downloading from: {update_url}")
            response = requests.get(update_url, timeout=30)
            response.raise_for_status()
            new_code = response.text
            
            # Extract version from new code
            new_version = "unknown"
            for line in new_code.split('\n'):
                if line.strip().startswith('VERSION = '):
                    new_version = line.split('"')[1]
                    break
            
            logger.info(f"📦 New version: {new_version}")
            
            # Backup current
            backup_file = f"{AGENT_FILE}.backup"
            logger.info(f"💾 Creating backup: {backup_file}")
            with open(AGENT_FILE, 'r') as f:
                with open(backup_file, 'w') as bf:
                    bf.write(f.read())
            
            # Write new code
            logger.info(f"📝 Writing new agent code...")
            with open(AGENT_FILE, 'w') as f:
                f.write(new_code)
            
            logger.info("=" * 60)
            logger.info(f"✅ UPDATE SUCCESSFUL!")
            logger.info(f"   {self.version} → {new_version}")
            logger.info("🔄 Restarting agent service...")
            logger.info("=" * 60)
            
            # Schedule restart
            def restart():
                time.sleep(2)
                if sys.platform == 'darwin':
                    plist = os.path.expanduser('~/Library/LaunchAgents/com.remote-agent.plist')
                    subprocess.run(['launchctl', 'unload', plist], check=False)
                    subprocess.run(['launchctl', 'load', plist], check=False)
                else:
                    subprocess.run(['sudo', 'systemctl', 'restart', 'remote-agent'], check=False)
            
            threading.Thread(target=restart, daemon=True).start()
            
            return {
                "success": True,
                "message": f"Updated {self.version} → {new_version}",
                "old_version": self.version,
                "new_version": new_version,
                "restarting": True
            }
            
        except Exception as e:
            logger.error(f"❌ Update failed: {e}")
            return {"success": False, "error": str(e)}
    
    def execute_command(self, cmd: dict):
        cmd_id = cmd['id']
        command = cmd['command']
        if isinstance(command, str):
            command = json.loads(command)
        
        cmd_type = command.get('type')
        logger.info(f"📨 Command {cmd_id}: {cmd_type}")
        
        self.graphql.update_command_status(cmd_id, 'processing')
        
        try:
            result = None
            
            if cmd_type == 'ping':
                result = {"success": True, "message": "pong", "version": self.version}
            
            elif cmd_type == 'get_status':
                result = {
                    "success": True,
                    "agent_id": self.agent_id,
                    "version": self.version,
                    "release_date": RELEASE_DATE,
                    "plugins": self.plugin_manager.list_plugins(),
                    "ws_connected": self.ws_connected
                }
            
            elif cmd_type == 'self_update':
                update_url = command.get('url')
                result = self.self_update(update_url=update_url)
            
            elif cmd_type == 'plugin_command':
                plugin_name = command.get('plugin')
                args = command.get('args', {})
                result = self.plugin_manager.execute_plugin(plugin_name, args)
            
            elif cmd_type == 'sync_plugins':
                self.sync_plugins()
                result = {"success": True, "plugins": self.plugin_manager.list_plugins()}
            
            elif cmd_type == 'list_plugins':
                result = {"success": True, "plugins": self.plugin_manager.list_plugins()}
            
            else:
                result = {"success": False, "error": f"Unknown command: {cmd_type}"}
            
            status = 'done' if result.get('success', True) else 'failed'
            self.graphql.update_command_status(cmd_id, status, result)
            logger.info(f"✓ Command {cmd_id}: {status}")
            
        except Exception as e:
            logger.error(f"✗ Command {cmd_id} failed: {e}")
            self.graphql.update_command_status(cmd_id, 'failed', {"error": str(e)})
    
    def poll_commands(self):
        commands = self.graphql.get_pending_commands(self.agent_id)
        for cmd in commands:
            self.execute_command(cmd)
    
    def heartbeat_loop(self):
        interval = self.config.get('agent.heartbeat_interval', 30)
        while self.running:
            try:
                self.graphql.report_heartbeat(self.agent_id, self.version, 'online')
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
            time.sleep(interval)
    
    def polling_loop(self):
        interval = self.config.get('agent.poll_interval', 60)
        while self.running:
            if not self.ws_connected:
                try:
                    self.poll_commands()
                except Exception as e:
                    logger.error(f"Polling failed: {e}")
            time.sleep(interval)
    
    def on_ws_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get('type') == 'new_command':
                self.execute_command(data.get('command'))
            elif data.get('type') == 'ping':
                ws.send(json.dumps({"type": "pong"}))
        except Exception as e:
            logger.error(f"WS message error: {e}")
    
    def on_ws_open(self, ws):
        logger.info("✅ WebSocket connected")
        self.ws_connected = True
        self.poll_commands()
    
    def on_ws_close(self, ws, code, msg):
        logger.warning(f"WebSocket closed: {code}")
        self.ws_connected = False
        time.sleep(5)
        if self.running:
            self.start_websocket()
    
    def on_ws_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
        self.ws_connected = False
    
    def start_websocket(self):
        ws_url = f"{self.config.get('server.ws_url')}?agentId={self.agent_id}"
        logger.info(f"Connecting to: {ws_url}")
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_message=self.on_ws_message,
            on_error=self.on_ws_error,
            on_close=self.on_ws_close,
            on_open=self.on_ws_open
        )
        threading.Thread(target=self.ws.run_forever, daemon=True).start()
    
    def start(self):
        logger.info("🚀 Starting agent v1.0.0...")
        try:
            self.sync_plugins()
        except Exception as e:
            logger.error(f"Plugin sync failed: {e}")
        
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()
        threading.Thread(target=self.polling_loop, daemon=True).start()
        self.start_websocket()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
            if self.ws:
                self.ws.close()


def main():
    agent = Agent()
    agent.start()


if __name__ == "__main__":
    main()
