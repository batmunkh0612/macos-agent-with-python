#!/bin/bash

# =============================================================================
# Remote Agent Updater
# =============================================================================
# Update existing installation with one command:
#   curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-update.sh | bash
#
# Custom repo:
#   curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-update.sh | bash -s -- --repo https://raw.githubusercontent.com/your-repo/main
#
# Custom install dir:
#   curl -fsSL ... | bash -s -- --dir /opt/remote-agent
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="/opt/remote-agent"
REPO_BASE="https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main"

while [[ $# -gt 0 ]]; do
    case $1 in
        --repo)
            REPO_BASE="$2"
            shift 2
            ;;
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo ""
echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}   Remote Agent Updater${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""

if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "${RED}Agent not installed at $INSTALL_DIR${NC}"
    echo "Install first: curl -fsSL $REPO_BASE/remote-install.sh | bash"
    exit 1
fi

# Stop the agent
echo -e "${YELLOW}Stopping agent...${NC}"
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLIST_FILE="$HOME/Library/LaunchAgents/com.remote-agent.plist"
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
else
    sudo systemctl stop remote-agent 2>/dev/null || true
fi
echo -e "${GREEN}Stopped${NC}"

# Backup config (never overwrite)
CONFIG_BACKUP="/tmp/remote-agent-config.yaml.backup"
if [ -f "$INSTALL_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/config.yaml" "$CONFIG_BACKUP"
    echo -e "${GREEN}Config backed up${NC}"
fi

# Download latest agent.py
echo -e "${YELLOW}Downloading latest agent...${NC}"
curl -fsSL "$REPO_BASE/agent.py" -o "$INSTALL_DIR/agent.py"
curl -fsSL "$REPO_BASE/requirements.txt" -o "$INSTALL_DIR/requirements.txt" 2>/dev/null || true

# Update plugins
for name in shell system nginx __init__; do
    curl -fsSL "$REPO_BASE/plugins/${name}.py" -o "$INSTALL_DIR/plugins/${name}.py" 2>/dev/null || true
done

# Restore config
if [ -f "$CONFIG_BACKUP" ]; then
    cp "$CONFIG_BACKUP" "$INSTALL_DIR/config.yaml"
    rm -f "$CONFIG_BACKUP"
    echo -e "${GREEN}Config restored${NC}"
fi

# Refresh dependencies
if [ -d "$INSTALL_DIR/venv" ]; then
    echo -e "${YELLOW}Refreshing dependencies...${NC}"
    "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt" 2>/dev/null || true
fi

# Start the agent
echo -e "${YELLOW}Starting agent...${NC}"
if [[ "$OSTYPE" == "darwin"* ]]; then
    launchctl load "$PLIST_FILE"
else
    sudo systemctl start remote-agent
fi

sleep 2
echo ""
echo -e "${GREEN}Agent updated successfully at $INSTALL_DIR${NC}"
echo ""

if [[ "$OSTYPE" == "darwin"* ]]; then
    launchctl list | grep remote-agent || true
    echo "Logs: tail -f $INSTALL_DIR/agent.log"
else
    sudo systemctl is-active remote-agent && echo "Status: running" || true
fi
echo ""
