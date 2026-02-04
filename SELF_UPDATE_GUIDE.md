# Self-Update Feature Guide

This guide explains how to test the self-update feature of the Remote Agent.

## Overview

The agent supports remote self-updates via:
1. **Direct URL** - Download from any URL (GitHub, custom server, etc.)
2. **Server Query** - Query GraphQL server for updates
3. **Auto-Update** - Periodic automatic updates

## Version Info

| Version | File | Description |
|---------|------|-------------|
| v1.0.0 | `releases/agent-v1.0.0.py` | Old version (basic features) |
| v2.0.0 | `agent.py` | New version (batch commands, auto-update) |

---

## Testing Self-Update (Step by Step)

### Step 1: Install the OLD Version (v1.0.0)

```bash
# Navigate to agent directory
cd /path/to/agent-management-platform-service/agent

# Copy OLD version to be installed
cp releases/agent-v1.0.0.py agent.py

# Install the agent
./install.sh
```

### Step 2: Verify Old Version is Running

Check the logs:
```bash
# macOS
tail -f /opt/remote-agent/agent.log
```

You should see:
```
============================================================
🤖 Agent v1.0.0 initialized
   Agent ID: imac-001
   Release: 2025-01-01
============================================================
```

Or send a status command:
```json
{
  "agentId": "imac-001",
  "command": {
    "type": "get_status"
  }
}
```

Response:
```json
{
  "success": true,
  "version": "1.0.0",
  "release_date": "2025-01-01"
}
```

### Step 3: Host the NEW Version

Option A: **Use GitHub Raw URL**
```
# Upload agent.py to your GitHub repo, then use:
https://raw.githubusercontent.com/YOUR_ORG/YOUR_REPO/main/agent/agent.py
```

Option B: **Use Local File Server**
```bash
# Start a simple HTTP server in the agent directory
cd /path/to/agent
python3 -m http.server 8080

# URL will be:
# http://YOUR_IP:8080/agent.py
```

Option C: **Copy to Public Cloud Storage**
- Upload to S3, GCS, or any public URL

### Step 4: Trigger Self-Update via GraphQL

Send this mutation:

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
    "type": "self_update",
    "url": "https://raw.githubusercontent.com/YOUR_ORG/YOUR_REPO/main/agent/agent.py"
  }
}
```

### Step 5: Watch the Update Logs

```bash
tail -f /opt/remote-agent/agent.log
```

You'll see:
```
============================================================
🔄 SELF-UPDATE PROCESS STARTED
   Current Version: 1.0.0
   Release Date: 2025-01-01
============================================================
📥 Downloading from URL: https://...
   Downloaded 28456 bytes
   Detected version: 2.0.0
   Checksum: a1b2c3d4e5f6...
✓ Checksum verified
💾 Creating backup: /opt/remote-agent/agent.py.backup
   Backup created successfully
📝 Writing new agent code to: /opt/remote-agent/agent.py
   New code written successfully
============================================================
✅ UPDATE SUCCESSFUL!
   Old Version: 1.0.0
   New Version: 2.0.0
============================================================
🔄 Scheduling agent restart in 2 seconds...
🔄 Executing restart...
```

### Step 6: Verify New Version

After restart, check logs:
```
============================================================
🤖 Agent v2.0.0 initialized
   Agent ID: imac-001
   Release: 2026-02-04
   Notes: Added batch commands, auto-update, improved plugin system
============================================================
```

---

## Update ALL Agents at Once

### Option 1: Broadcast to All Online Agents

```graphql
mutation BroadcastCommand($command: JSON!) {
  broadcastCommand(command: $command) {
    success
    totalAgents
    commands { id agentId }
  }
}
```

```json
{
  "command": {
    "type": "self_update",
    "url": "https://your-server.com/agent.py"
  }
}
```

### Option 2: Batch Update Specific Agents

```graphql
mutation BatchCommand($agentIds: [String!]!, $command: JSON!) {
  batchCommand(agentIds: $agentIds, command: $command) {
    success
    totalAgents
  }
}
```

```json
{
  "agentIds": ["imac-001", "imac-002", "macbook-001"],
  "command": {
    "type": "self_update",
    "url": "https://your-server.com/agent.py"
  }
}
```

---

## Enable Auto-Update

Edit `/opt/remote-agent/config.yaml`:

```yaml
updates:
  auto_update: true
  check_interval: 3600  # Check every hour
  update_url: "https://your-server.com/agent.py"
```

The agent will automatically:
1. Check for updates every hour
2. Download and verify new version
3. Apply update and restart

---

## Rollback to Previous Version

If something goes wrong:

```bash
# The old version is automatically backed up
cd /opt/remote-agent
cp agent.py.backup agent.py

# Restart the agent
# macOS:
launchctl unload ~/Library/LaunchAgents/com.remote-agent.plist
launchctl load ~/Library/LaunchAgents/com.remote-agent.plist

# Linux:
sudo systemctl restart remote-agent
```

---

## Command Response Examples

### Successful Update
```json
{
  "success": true,
  "message": "Updated from 1.0.0 to 2.0.0",
  "old_version": "1.0.0",
  "new_version": "2.0.0",
  "restarting": true
}
```

### No Update Available
```json
{
  "success": true,
  "message": "Already at latest version 2.0.0",
  "current_version": "2.0.0"
}
```

### Update Failed
```json
{
  "success": false,
  "error": "Checksum mismatch - update rejected"
}
```

---

## Troubleshooting

### Update Downloaded but Agent Didn't Restart

Check if launchd/systemd has permission to restart:
```bash
# macOS - check plist exists
ls -la ~/Library/LaunchAgents/com.remote-agent.plist

# Manually restart
launchctl unload ~/Library/LaunchAgents/com.remote-agent.plist
launchctl load ~/Library/LaunchAgents/com.remote-agent.plist
```

### Download Failed

Check network connectivity:
```bash
curl -I https://your-update-url.com/agent.py
```

### Checksum Mismatch

The downloaded file might be corrupted or cached. Try:
```bash
# Force fresh download (if using CDN)
curl -H "Cache-Control: no-cache" https://your-url/agent.py
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-01-01 | Initial release |
| 2.0.0 | 2026-02-04 | Batch commands, auto-update, improved plugins |
