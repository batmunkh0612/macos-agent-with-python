#!/bin/bash

# =============================================================================
# Remote Agent Installer
# =============================================================================
# Install with:
#   curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-install.sh | bash
#
# Or with custom agent ID:
#   curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-install.sh | bash -s -- --id my-agent-001
#
# Or with custom server:
#   curl -fsSL https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main/remote-install.sh | bash -s -- --id my-agent --server https://my-server.com
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
INSTALL_DIR="/opt/remote-agent"
AGENT_ID=""
SERVER_URL="https://agent-management-platform-service-test.shagai.workers.dev"
REPO_BASE="https://raw.githubusercontent.com/batmunkh0612/macos-agent-with-python/main"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --id)
            AGENT_ID="$2"
            shift 2
            ;;
        --server)
            SERVER_URL="$2"
            shift 2
            ;;
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
echo -e "${BLUE}   🚀 Remote Agent Installer${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""

# Check Python
echo -e "${YELLOW}Checking prerequisites...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is required but not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python 3 found${NC}"

# Create install directory
echo -e "${YELLOW}Creating install directory...${NC}"
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$INSTALL_DIR/plugins"

# Set ownership
CURRENT_USER=$(whoami)
if [[ "$OSTYPE" == "darwin"* ]]; then
    CURRENT_GROUP=$(id -gn)
    sudo chown -R "$CURRENT_USER:$CURRENT_GROUP" "$INSTALL_DIR"
else
    sudo chown -R "$USER:$USER" "$INSTALL_DIR"
fi
echo -e "${GREEN}✓ Directory created: $INSTALL_DIR${NC}"

# Download files
echo -e "${YELLOW}Downloading agent files...${NC}"

echo "  Downloading agent.py..."
curl -fsSL "$REPO_BASE/agent.py" -o "$INSTALL_DIR/agent.py"

echo "  Downloading requirements.txt..."
curl -fsSL "$REPO_BASE/requirements.txt" -o "$INSTALL_DIR/requirements.txt"

echo "  Downloading plugins..."
curl -fsSL "$REPO_BASE/plugins/shell.py" -o "$INSTALL_DIR/plugins/shell.py" 2>/dev/null || true
curl -fsSL "$REPO_BASE/plugins/system.py" -o "$INSTALL_DIR/plugins/system.py" 2>/dev/null || true
curl -fsSL "$REPO_BASE/plugins/nginx.py" -o "$INSTALL_DIR/plugins/nginx.py" 2>/dev/null || true
curl -fsSL "$REPO_BASE/plugins/__init__.py" -o "$INSTALL_DIR/plugins/__init__.py" 2>/dev/null || true

echo -e "${GREEN}✓ Files downloaded${NC}"

# Generate config
echo -e "${YELLOW}Generating configuration...${NC}"

# Use hostname if agent ID not provided
if [ -z "$AGENT_ID" ]; then
    AGENT_ID=$(hostname | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
fi

cat > "$INSTALL_DIR/config.yaml" << EOF
server:
  ws_url: wss://${SERVER_URL#https://}/ws
  graphql_url: ${SERVER_URL}/graphql

agent:
  id: ${AGENT_ID}
  heartbeat_interval: 30
  poll_interval: 60

plugins:
  auto_sync: true
  sync_interval: 300

updates:
  auto_update: false
  check_interval: 3600
  update_url: "${REPO_BASE}/agent.py"
EOF

echo -e "${GREEN}✓ Config generated (Agent ID: $AGENT_ID)${NC}"

# Create virtual environment and install dependencies
echo -e "${YELLOW}Setting up Python environment...${NC}"
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Setup service
echo -e "${YELLOW}Setting up system service...${NC}"

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - launchd
    mkdir -p "$HOME/Library/LaunchAgents"
    PLIST_FILE="$HOME/Library/LaunchAgents/com.remote-agent.plist"
    
    cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.remote-agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/venv/bin/python</string>
        <string>$INSTALL_DIR/agent.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/agent.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/agent.error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
EOF
    
    # Load service
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    launchctl load "$PLIST_FILE"
    
    echo -e "${GREEN}✓ Service installed (launchd)${NC}"
    
    echo ""
    echo -e "${BLUE}=============================================${NC}"
    echo -e "${GREEN}✅ Installation Complete!${NC}"
    echo -e "${BLUE}=============================================${NC}"
    echo ""
    echo -e "Agent ID:    ${YELLOW}$AGENT_ID${NC}"
    echo -e "Install Dir: ${YELLOW}$INSTALL_DIR${NC}"
    echo -e "Server:      ${YELLOW}$SERVER_URL${NC}"
    echo ""
    echo -e "${BLUE}Commands:${NC}"
    echo "  View logs:  tail -f $INSTALL_DIR/agent.log"
    echo "  Stop:       launchctl unload $PLIST_FILE"
    echo "  Start:      launchctl load $PLIST_FILE"
    echo "  Status:     launchctl list | grep remote-agent"
    echo ""
    
else
    # Linux - systemd
    cat << EOF | sudo tee /etc/systemd/system/remote-agent.service > /dev/null
[Unit]
Description=Remote Agent
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/agent.py
Restart=always
RestartSec=10
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF
    
    # Enable and start
    sudo systemctl daemon-reload
    sudo systemctl enable remote-agent
    sudo systemctl start remote-agent
    
    echo -e "${GREEN}✓ Service installed (systemd)${NC}"
    
    echo ""
    echo -e "${BLUE}=============================================${NC}"
    echo -e "${GREEN}✅ Installation Complete!${NC}"
    echo -e "${BLUE}=============================================${NC}"
    echo ""
    echo -e "Agent ID:    ${YELLOW}$AGENT_ID${NC}"
    echo -e "Install Dir: ${YELLOW}$INSTALL_DIR${NC}"
    echo -e "Server:      ${YELLOW}$SERVER_URL${NC}"
    echo ""
    echo -e "${BLUE}Commands:${NC}"
    echo "  View logs:  sudo journalctl -u remote-agent -f"
    echo "  Stop:       sudo systemctl stop remote-agent"
    echo "  Start:      sudo systemctl start remote-agent"
    echo "  Status:     sudo systemctl status remote-agent"
    echo ""
fi
