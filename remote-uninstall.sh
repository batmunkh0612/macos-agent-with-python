#!/bin/bash

# =============================================================================
# Remote Agent Uninstaller
# =============================================================================
# Uninstall with:
#   curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-uninstall.sh | bash
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="/opt/remote-agent"
PLIST_FILE="$HOME/Library/LaunchAgents/com.remote-agent.plist"

echo ""
echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}   🗑️  Remote Agent Uninstaller${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""

# Stop and remove service
echo -e "${YELLOW}Stopping service...${NC}"

if [[ "$OSTYPE" == "darwin"* ]]; then
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    rm -f "$PLIST_FILE"
    echo -e "${GREEN}✓ macOS service removed${NC}"
else
    sudo systemctl stop remote-agent 2>/dev/null || true
    sudo systemctl disable remote-agent 2>/dev/null || true
    sudo rm -f /etc/systemd/system/remote-agent.service
    sudo systemctl daemon-reload
    echo -e "${GREEN}✓ Linux service removed${NC}"
fi

# Remove files
echo -e "${YELLOW}Removing files...${NC}"
sudo rm -rf "$INSTALL_DIR"
echo -e "${GREEN}✓ Files removed${NC}"

echo ""
echo -e "${GREEN}✅ Agent uninstalled successfully!${NC}"
echo ""
