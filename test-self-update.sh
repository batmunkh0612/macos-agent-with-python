#!/bin/bash

# Test Self-Update Feature
# This script helps you test the agent's self-update capability

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/remote-agent"

echo "=========================================="
echo "🧪 Self-Update Test Script"
echo "=========================================="
echo ""

# Menu
echo "Choose an option:"
echo ""
echo "  1) Install OLD version (v1.0.0)"
echo "  2) Install NEW version (v2.0.0)"
echo "  3) Check current installed version"
echo "  4) Start local file server (for testing)"
echo "  5) View agent logs"
echo "  6) Restart agent"
echo "  7) Rollback to backup"
echo ""
read -p "Enter choice [1-7]: " choice

case $choice in
    1)
        echo ""
        echo "📦 Installing OLD version (v1.0.0)..."
        echo ""
        
        # Copy old version
        cp "$SCRIPT_DIR/releases/agent-v1.0.0.py" "$SCRIPT_DIR/agent.py"
        
        # Run install
        cd "$SCRIPT_DIR"
        ./install.sh
        
        echo ""
        echo "✅ OLD version installed!"
        echo "   Check logs: tail -f $INSTALL_DIR/agent.log"
        ;;
        
    2)
        echo ""
        echo "📦 Installing NEW version (v2.0.0)..."
        echo ""
        
        # Restore new version from git or use current
        git checkout "$SCRIPT_DIR/agent.py" 2>/dev/null || true
        
        # Run install
        cd "$SCRIPT_DIR"
        ./install.sh
        
        echo ""
        echo "✅ NEW version installed!"
        echo "   Check logs: tail -f $INSTALL_DIR/agent.log"
        ;;
        
    3)
        echo ""
        echo "🔍 Checking installed version..."
        echo ""
        
        if [ -f "$INSTALL_DIR/agent.py" ]; then
            VERSION=$(grep "^VERSION = " "$INSTALL_DIR/agent.py" | head -1 | cut -d'"' -f2)
            RELEASE=$(grep "^RELEASE_DATE = " "$INSTALL_DIR/agent.py" | head -1 | cut -d'"' -f2)
            
            echo "   Version: $VERSION"
            echo "   Release: $RELEASE"
            echo ""
            echo "   File: $INSTALL_DIR/agent.py"
        else
            echo "   Agent not installed at $INSTALL_DIR"
        fi
        ;;
        
    4)
        echo ""
        echo "🌐 Starting local file server..."
        echo ""
        echo "   URL: http://$(ipconfig getifaddr en0 2>/dev/null || hostname -I | awk '{print $1}'):8080/agent.py"
        echo ""
        echo "   Use this URL in the self_update command:"
        echo '   {"type": "self_update", "url": "http://YOUR_IP:8080/agent.py"}'
        echo ""
        echo "   Press Ctrl+C to stop the server"
        echo ""
        
        cd "$SCRIPT_DIR"
        python3 -m http.server 8080
        ;;
        
    5)
        echo ""
        echo "📜 Viewing agent logs..."
        echo ""
        
        if [ -f "$INSTALL_DIR/agent.log" ]; then
            tail -f "$INSTALL_DIR/agent.log"
        else
            echo "   Log file not found: $INSTALL_DIR/agent.log"
        fi
        ;;
        
    6)
        echo ""
        echo "🔄 Restarting agent..."
        echo ""
        
        PLIST="$HOME/Library/LaunchAgents/com.remote-agent.plist"
        
        if [[ "$OSTYPE" == "darwin"* ]]; then
            launchctl unload "$PLIST" 2>/dev/null || true
            launchctl load "$PLIST"
            echo "   Agent restarted (macOS)"
        else
            sudo systemctl restart remote-agent
            echo "   Agent restarted (Linux)"
        fi
        ;;
        
    7)
        echo ""
        echo "⏪ Rolling back to backup..."
        echo ""
        
        if [ -f "$INSTALL_DIR/agent.py.backup" ]; then
            sudo cp "$INSTALL_DIR/agent.py.backup" "$INSTALL_DIR/agent.py"
            
            # Restart
            PLIST="$HOME/Library/LaunchAgents/com.remote-agent.plist"
            if [[ "$OSTYPE" == "darwin"* ]]; then
                launchctl unload "$PLIST" 2>/dev/null || true
                launchctl load "$PLIST"
            else
                sudo systemctl restart remote-agent
            fi
            
            echo "   ✅ Rolled back and restarted!"
        else
            echo "   ❌ No backup found at $INSTALL_DIR/agent.py.backup"
        fi
        ;;
        
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
