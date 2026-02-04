#!/bin/bash

# Test script to check agent status and logs

echo "🔍 Checking Agent Status..."
echo ""

# Check if agent is running
echo "1. Process Status:"
launchctl list | grep remote-agent || echo "   ❌ Agent not found in launchctl"
echo ""

# Check log files
INSTALL_DIR="/opt/remote-agent"
echo "2. Log Files:"
echo "   Main log: $INSTALL_DIR/agent.log"
if [ -f "$INSTALL_DIR/agent.log" ]; then
    echo "   ✅ Log file exists"
    echo "   Last 20 lines:"
    tail -20 "$INSTALL_DIR/agent.log"
else
    echo "   ❌ Log file not found"
fi
echo ""

echo "   Error log: $INSTALL_DIR/agent.error.log"
if [ -f "$INSTALL_DIR/agent.error.log" ]; then
    echo "   ✅ Error log exists"
    echo "   Last 20 lines:"
    tail -20 "$INSTALL_DIR/agent.error.log"
else
    echo "   ❌ Error log not found"
fi
echo ""

# Check config
echo "3. Configuration:"
if [ -f "$INSTALL_DIR/config.yaml" ]; then
    echo "   ✅ Config file exists"
    echo "   Agent ID:"
    grep "id:" "$INSTALL_DIR/config.yaml" | head -1
else
    echo "   ❌ Config file not found"
fi
echo ""

# Check if Python process is running
echo "4. Python Process:"
ps aux | grep "[a]gent.py" || echo "   ❌ No agent.py process found"
echo ""

# Test GraphQL connection
echo "5. Testing GraphQL Connection:"
GRAPHQL_URL=$(grep "graphql_url:" "$INSTALL_DIR/config.yaml" 2>/dev/null | awk '{print $2}' || echo "https://agent-management-platform-service-test.shagai.workers.dev/graphql")
echo "   URL: $GRAPHQL_URL"
curl -s -X POST "$GRAPHQL_URL" \
  -H "Content-Type: application/json" \
  -d '{"query":"{ __typename }"}' | head -1
echo ""
echo ""

# Check agent heartbeat
AGENT_ID=$(grep "id:" "$INSTALL_DIR/config.yaml" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"' || echo "imac-001")
echo "6. Checking Agent Heartbeat (Agent ID: $AGENT_ID):"
curl -s -X POST "$GRAPHQL_URL" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"query { getAgentStatus(agentId: \\\"$AGENT_ID\\\") { agentId status lastSeen hostname } }\"}" | python3 -m json.tool 2>/dev/null || echo "   Could not parse response"
echo ""

echo "✅ Diagnostic complete!"
