#!/bin/bash

# Agent update script - stops, updates files, and restarts the agent

set -e

echo "🔄 Updating Remote Agent..."

INSTALL_DIR="/opt/remote-agent"
PLIST_FILE="$HOME/Library/LaunchAgents/com.remote-agent.plist"

# Check if agent is installed
if [ ! -d "$INSTALL_DIR" ]; then
    echo "❌ Agent not installed. Run ./install.sh first."
    exit 1
fi

# Stop the agent
echo "⏹️  Stopping agent..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
else
    # Linux
    sudo systemctl stop remote-agent 2>/dev/null || true
fi

# Backup config
echo "📦 Backing up configuration..."
cp "$INSTALL_DIR/config.yaml" "/tmp/config.yaml.backup" 2>/dev/null || true

# Update files
echo "📝 Updating agent files..."
sudo cp agent.py "$INSTALL_DIR/"
sudo cp -r plugins/* "$INSTALL_DIR/plugins/"

# Restore config (in case it was overwritten)
if [ -f "/tmp/config.yaml.backup" ]; then
    sudo cp "/tmp/config.yaml.backup" "$INSTALL_DIR/config.yaml"
fi

# Fix permissions
if [[ "$OSTYPE" == "darwin"* ]]; then
    sudo chown -R $(whoami):staff "$INSTALL_DIR"
else
    sudo chown -R $USER:$USER "$INSTALL_DIR"
fi

# Start the agent
echo "▶️  Starting agent..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    launchctl load "$PLIST_FILE"
else
    # Linux
    sudo systemctl start remote-agent
fi

# Wait a moment for startup
sleep 2

# Show status
echo ""
echo "✅ Agent updated successfully!"
echo ""

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "📋 Status:"
    launchctl list | grep remote-agent || echo "   (not running)"
    echo ""
    echo "📜 Recent logs:"
    tail -10 "$INSTALL_DIR/agent.log" 2>/dev/null || echo "   (no logs yet)"
else
    echo "📋 Status:"
    sudo systemctl status remote-agent --no-pager | head -10
fi
