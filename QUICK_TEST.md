# Quick Test Guide

## 1. Check Agent Status

Run the diagnostic script:
```bash
cd /opt/remote-agent
./test-agent.sh
```

Or manually check:

```bash
# Check if process is running
ps aux | grep agent.py

# Check log files
tail -f /opt/remote-agent/agent.log
tail -f /opt/remote-agent/agent.error.log

# Check launchd status
launchctl list | grep remote-agent
```

## 2. If Logs Are Empty - Manual Test

Stop the service and run manually to see errors:

```bash
# Stop the service
launchctl unload ~/Library/LaunchAgents/com.remote-agent.plist

# Run manually to see output
cd /opt/remote-agent
source venv/bin/activate
python agent.py
```

This will show you any errors in real-time.

## 3. Test GraphQL Connection

```bash
# Get your agent ID from config
AGENT_ID=$(grep "id:" /opt/remote-agent/config.yaml | head -1 | awk '{print $2}' | tr -d '"')

# Check if agent has sent heartbeat
curl -X POST https://agent-management-platform-service-test.shagai.workers.dev/graphql \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"query { getAgentStatus(agentId: \\\"$AGENT_ID\\\") { agentId status lastSeen hostname } }\"}"
```

## 4. Send a Test Command

```bash
# Send ping command
curl -X POST https://agent-management-platform-service-test.shagai.workers.dev/graphql \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"mutation CreateCmd(\$agentId: String!, \$command: JSON!) { createCommand(agentId: \$agentId, command: \$command) { id status } }\",
    \"variables\": {
      \"agentId\": \"$AGENT_ID\",
      \"command\": { \"type\": \"ping\" }
    }
  }"
```

## 5. Check Command History

```bash
curl -X POST https://agent-management-platform-service-test.shagai.workers.dev/graphql \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"query(\$agentId: String!) { getCommandHistory(agentId: \$agentId, limit: 5) { id command status result } }\",
    \"variables\": { \"agentId\": \"$AGENT_ID\" }
  }"
```

## Common Issues

### Logs Empty
- Check error log: `cat /opt/remote-agent/agent.error.log`
- Run manually to see errors: `cd /opt/remote-agent && source venv/bin/activate && python agent.py`
- Check Python path in plist matches venv

### Agent Not Connecting
- Verify config.yaml has correct URLs
- Check network connectivity
- Verify Python dependencies installed: `pip list | grep websocket`

### No Heartbeat
- Check if agent can reach GraphQL endpoint
- Verify agent ID matches in config and database
- Check error logs for connection issues
