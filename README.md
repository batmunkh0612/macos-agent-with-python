# Python Remote Agent

A self-updating Python agent that connects to the Agent Management Platform via WebSocket and GraphQL.

## Features

- **Real-time Communication**: WebSocket connection for instant command delivery
- **Fallback Polling**: Automatic fallback to HTTP polling when WebSocket is unavailable
- **Plugin System**: Dynamic plugin loading with local and remote plugins
- **Auto-sync**: Automatic plugin synchronization from server
- **Heartbeat Monitoring**: Periodic status reporting to server
- **Cross-platform**: Supports macOS (launchd) and Linux (systemd)

---

## Quick Start

### One-Line Install (from GitHub)

```bash
# Basic install (uses hostname as agent ID)
curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-install.sh | bash

# With custom agent ID
curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-install.sh | bash -s -- --id my-macbook-001

# With custom agent ID and server
curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-install.sh | bash -s -- --id my-agent --server https://my-server.workers.dev
```

### One-Line Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-uninstall.sh | bash
```

---

## Installation Options

### Option 1: Remote Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-install.sh | bash -s -- --id my-agent-001
```

Parameters:
- `--id <name>` - Agent ID (default: hostname)
- `--server <url>` - Server URL (default: test server)
- `--repo <url>` - Repository base URL
- `--dir <path>` - Install directory (default: /opt/remote-agent)

### Option 2: Local Install

```bash
# Clone or download the agent folder
git clone https://github.com/batmunkh0612/macos-agent-with-python.git
cd macos-agent-with-python

# Configure
nano config.yaml

# Install
./install.sh
```

### Prerequisites

- Python 3.8+
- curl (for remote install)
- sudo access

The script will:
1. Create `/opt/remote-agent` directory
2. Copy agent files and plugins
3. Create Python virtual environment
4. Install dependencies
5. Configure system service (launchd on macOS, systemd on Linux)
6. Start the agent

---

## Uninstallation

### macOS

```bash
# 1. Stop and unload the service
launchctl unload ~/Library/LaunchAgents/com.remote-agent.plist

# 2. Remove the plist file
rm ~/Library/LaunchAgents/com.remote-agent.plist

# 3. Remove installation directory
sudo rm -rf /opt/remote-agent

echo "✅ Agent uninstalled"
```

### Linux

```bash
# 1. Stop and disable the service
sudo systemctl stop remote-agent
sudo systemctl disable remote-agent

# 2. Remove service file
sudo rm /etc/systemd/system/remote-agent.service
sudo systemctl daemon-reload

# 3. Remove installation directory
sudo rm -rf /opt/remote-agent

echo "✅ Agent uninstalled"
```

---

## Update Agent

### Quick Update (Recommended)

```bash
# Navigate to source directory with updated code
cd /path/to/agent

# Stop, reinstall, and start
./update.sh  # or manually:

# macOS
launchctl unload ~/Library/LaunchAgents/com.remote-agent.plist
./install.sh

# Linux
sudo systemctl stop remote-agent
./install.sh
```

### Manual Update

```bash
# 1. Stop the agent
# macOS:
launchctl unload ~/Library/LaunchAgents/com.remote-agent.plist
# Linux:
sudo systemctl stop remote-agent

# 2. Copy updated files
sudo cp agent.py /opt/remote-agent/
sudo cp -r plugins/* /opt/remote-agent/plugins/

# 3. Start the agent
# macOS:
launchctl load ~/Library/LaunchAgents/com.remote-agent.plist
# Linux:
sudo systemctl start remote-agent
```

---

## Service Management Commands

### macOS (launchd)

| Action | Command |
|--------|---------|
| **Start** | `launchctl load ~/Library/LaunchAgents/com.remote-agent.plist` |
| **Stop** | `launchctl unload ~/Library/LaunchAgents/com.remote-agent.plist` |
| **Restart** | Stop then Start |
| **Status** | `launchctl list \| grep remote-agent` |
| **View Logs** | `tail -f /opt/remote-agent/agent.log` |
| **View Errors** | `tail -f /opt/remote-agent/agent.error.log` |

### Linux (systemd)

| Action | Command |
|--------|---------|
| **Start** | `sudo systemctl start remote-agent` |
| **Stop** | `sudo systemctl stop remote-agent` |
| **Restart** | `sudo systemctl restart remote-agent` |
| **Status** | `sudo systemctl status remote-agent` |
| **Enable (boot)** | `sudo systemctl enable remote-agent` |
| **Disable (boot)** | `sudo systemctl disable remote-agent` |
| **View Logs** | `sudo journalctl -u remote-agent -f` |

### Manual Run (Debug Mode)

```bash
cd /opt/remote-agent
source venv/bin/activate
python agent.py
```

---

## Configuration

Edit `config.yaml` before installation:

```yaml
server:
  ws_url: wss://agent-management-platform-service-test.shagai.workers.dev/ws
  graphql_url: https://agent-management-platform-service-test.shagai.workers.dev/graphql

agent:
  id: my-agent-001      # Unique agent ID (uses hostname if not set)
  heartbeat_interval: 30  # seconds
  poll_interval: 60       # fallback polling interval when WebSocket is down

plugins:
  auto_sync: true         # Auto-sync plugins from server
  sync_interval: 300      # 5 minutes

# Auto-update settings
updates:
  auto_update: false      # Set to true to enable automatic updates
  check_interval: 3600    # Check for updates every hour (in seconds)
  update_url: ""          # Optional: Direct URL to download updates from
```

### Auto-Update Configuration

Enable automatic updates by setting `auto_update: true`:

```yaml
updates:
  auto_update: true
  check_interval: 3600    # Check every hour
  update_url: "https://raw.githubusercontent.com/your-repo/main/agent/agent.py"
```

When enabled, the agent will:
1. Check for updates at the specified interval
2. Download and verify the new version
3. Apply the update and restart automatically

---

## Built-in Commands

Send these commands via the GraphQL API:

| Command | Description | Example Payload |
|---------|-------------|-----------------|
| `ping` | Health check | `{"type": "ping"}` |
| `get_status` | Get agent info | `{"type": "get_status"}` |
| `list_plugins` | List available plugins | `{"type": "list_plugins"}` |
| `sync_plugins` | Sync plugins from server | `{"type": "sync_plugins"}` |
| `reload_plugins` | Reload local plugins | `{"type": "reload_plugins"}` |
| `plugin_command` | Execute a plugin | See below |
| `self_update` | Update agent from server/URL | See below |
| `check_update` | Check if update available | `{"type": "check_update"}` |
| `update_plugin` | Update plugin from URL | See below |
| `restart` | Restart the agent | `{"type": "restart"}` |

### Plugin Command Example

```json
{
  "type": "plugin_command",
  "plugin": "shell",
  "args": {
    "script": "echo hello",
    "timeout": 10
  }
}
```

---

## Remote Update Commands

### Check for Updates

```json
{
  "type": "check_update"
}
```

Response:
```json
{
  "success": true,
  "update_available": true,
  "current_version": "1.0.1",
  "new_version": "1.0.2",
  "release_notes": "Bug fixes and improvements"
}
```

### Self-Update from Server

The server must implement the `getAgentUpdate` GraphQL query.

```json
{
  "type": "self_update"
}
```

### Self-Update from URL

Update directly from a URL (e.g., GitHub raw file):

```json
{
  "type": "self_update",
  "url": "https://raw.githubusercontent.com/your-repo/main/agent/agent.py",
  "force": false
}
```

### Update Plugin from URL

```json
{
  "type": "update_plugin",
  "name": "shell",
  "url": "https://raw.githubusercontent.com/your-repo/main/agent/plugins/shell.py"
}
```

### Restart Agent

```json
{
  "type": "restart"
}
```

---

## Server-Side GraphQL Schema for Updates

To enable self-updates from the server, implement this GraphQL query:

```graphql
type AgentUpdate {
  version: String!
  code: String!
  checksum: String!
  releaseNotes: String
}

type Query {
  getAgentUpdate(currentVersion: String!): AgentUpdate
}
```

The server should:
1. Compare `currentVersion` with the latest version
2. Return `null` if no update needed
3. Return the update info with code and SHA256 checksum

---

## Available Plugins

### shell - Execute Shell Commands

```json
{
  "type": "plugin_command",
  "plugin": "shell",
  "args": {
    "script": "ls -la /tmp",
    "timeout": 30,
    "cwd": "/home/user"
  }
}
```

### system - System Information

```json
{
  "type": "plugin_command",
  "plugin": "system",
  "args": {
    "action": "info"
  }
}
```

Actions: `info`, `disk`, `memory`, `cpu`

### nginx - Nginx Management

```json
{
  "type": "plugin_command",
  "plugin": "nginx",
  "args": {
    "action": "status"
  }
}
```

Actions: `status`, `reload`, `test`, `start`, `stop`

---

## GraphQL API Examples

### Send a Command to Single Agent

```graphql
mutation CreateCommand($agentId: String!, $command: JSON!) {
  createCommand(agentId: $agentId, command: $command) {
    id
    status
  }
}
```

Variables:
```json
{
  "agentId": "imac-001",
  "command": {
    "type": "ping"
  }
}
```

### Batch Command - Send to Multiple Agents

```graphql
mutation BatchCommand($agentIds: [String!]!, $command: JSON!) {
  batchCommand(agentIds: $agentIds, command: $command) {
    success
    totalAgents
    commands {
      id
      agentId
      status
    }
    errors
  }
}
```

Variables:
```json
{
  "agentIds": ["imac-001", "imac-002", "macbook-pro-001"],
  "command": {
    "type": "self_update",
    "url": "https://raw.githubusercontent.com/your-repo/main/agent/agent.py"
  }
}
```

### Broadcast Command - Send to ALL Online Agents

```graphql
mutation BroadcastCommand($command: JSON!) {
  broadcastCommand(command: $command) {
    success
    totalAgents
    commands {
      id
      agentId
      status
    }
    errors
  }
}
```

Variables:
```json
{
  "command": {
    "type": "self_update",
    "url": "https://raw.githubusercontent.com/your-repo/main/agent/agent.py"
  }
}
```

### Check Command Status

```graphql
query GetCommand($id: Int!) {
  getCommand(id: $id) {
    id
    status
    result
    createdAt
    completedAt
  }
}
```

### Get Online Agents

```graphql
query GetOnlineAgents {
  getOnlineAgents {
    agentId
    hostname
    ipAddress
    version
    lastHeartbeat
  }
}
```

---

## Troubleshooting

### Agent Not Starting

```bash
# Check if service is loaded (macOS)
launchctl list | grep remote-agent

# Check logs for errors
tail -100 /opt/remote-agent/agent.log
tail -100 /opt/remote-agent/agent.error.log
```

### Plugins Not Loading

```bash
# Check plugin directory
ls -la /opt/remote-agent/plugins/

# Run manually to see debug output
cd /opt/remote-agent
source venv/bin/activate
python agent.py
```

Expected output:
```
Plugin directory: /opt/remote-agent/plugins
Found files in plugins dir: ['__init__.py', 'nginx.py', 'shell.py', 'system.py']
✅ Local plugin loaded: nginx
✅ Local plugin loaded: shell
✅ Local plugin loaded: system
```

### WebSocket Connection Issues

```bash
# Test WebSocket with wscat
npm install -g wscat
wscat -c "wss://agent-management-platform-service-test.shagai.workers.dev/ws?agentId=test"
```

### GraphQL Connection Issues

```bash
# Test GraphQL endpoint
curl -X POST https://agent-management-platform-service-test.shagai.workers.dev/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "{ getPlugins { name } }"}'
```

### Permission Issues

```bash
# Fix ownership (macOS)
sudo chown -R $(whoami):staff /opt/remote-agent

# Fix ownership (Linux)
sudo chown -R $USER:$USER /opt/remote-agent
```

---

## File Structure

```
/opt/remote-agent/
├── agent.py           # Main agent script
├── config.yaml        # Configuration file
├── requirements.txt   # Python dependencies
├── agent.log          # Standard output log (macOS)
├── agent.error.log    # Error log (macOS)
├── venv/              # Python virtual environment
└── plugins/           # Plugin directory
    ├── __init__.py
    ├── shell.py       # Shell command plugin
    ├── system.py      # System info plugin
    └── nginx.py       # Nginx management plugin
```

---

## Plugin Development

Create a new plugin in `plugins/` directory:

```python
"""
My custom plugin
"""

import logging

logger = logging.getLogger("Plugin.MyPlugin")


def handle(args: dict) -> dict:
    """
    Handle plugin command.
    
    Args:
        args: Dictionary with command arguments
    
    Returns:
        Dictionary with 'success' and result/error
    """
    action = args.get("action", "default")
    
    logger.info("Executing action: %s", action)
    
    try:
        # Your plugin logic here
        result = {"message": f"Action {action} completed"}
        return {"success": True, **result}
    except Exception as e:
        logger.error("Plugin failed: %s", e)
        return {"success": False, "error": str(e)}
```

After adding a new plugin, either restart the agent or send a `reload_plugins` command.

---

## Security Notes

- Plugins execute with the same permissions as the agent process
- The shell plugin can run arbitrary commands - use with caution
- Plugin checksums are verified when synced from server
- Consider running in a container for additional isolation
- Use firewall rules to restrict agent communication

---

## Version History

- **1.0.1** - Fixed plugin path resolution, added better logging
- **1.0.0** - Initial release
