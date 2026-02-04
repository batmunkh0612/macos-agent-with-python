#!/bin/bash

# Agent uninstall script

set -e

echo "🗑️  Uninstalling Remote Agent..."

INSTALL_DIR="/opt/remote-agent"
PLIST_FILE="$HOME/Library/LaunchAgents/com.remote-agent.plist"

# Confirm uninstall
read -p "Are you sure you want to uninstall the agent? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# Stop the agent
echo "⏹️  Stopping agent..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    
    # Remove plist
    echo "📄 Removing launch agent..."
    rm -f "$PLIST_FILE"
else
    # Linux
    sudo systemctl stop remote-agent 2>/dev/null || true
    sudo systemctl disable remote-agent 2>/dev/null || true
    
    # Remove systemd service
    echo "📄 Removing systemd service..."
    sudo rm -f /etc/systemd/system/remote-agent.service
    sudo systemctl daemon-reload
fi

# Remove installation directory
echo "📁 Removing installation directory..."
sudo rm -rf "$INSTALL_DIR"

echo ""
echo "✅ Agent uninstalled successfully!"
