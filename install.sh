#!/bin/bash

# Agent installation script

set -e

echo "🚀 Installing Remote Agent..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required"
    exit 1
fi

# Create directory
INSTALL_DIR="/opt/remote-agent"
sudo mkdir -p $INSTALL_DIR

# Get current user and group (works on both Linux and macOS)
CURRENT_USER=$(whoami)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    CURRENT_GROUP=$(id -gn)
    sudo chown $CURRENT_USER:$CURRENT_GROUP $INSTALL_DIR
else
    # Linux
    sudo chown $USER:$USER $INSTALL_DIR
fi

# Copy files
cp agent.py $INSTALL_DIR/
cp requirements.txt $INSTALL_DIR/
cp config.yaml $INSTALL_DIR/
mkdir -p $INSTALL_DIR/plugins
cp plugins/*.py $INSTALL_DIR/plugins/ 2>/dev/null || true

# Install dependencies
cd $INSTALL_DIR
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create systemd service (Linux only)
if [[ "$OSTYPE" != "darwin"* ]]; then
    cat << EOF | sudo tee /etc/systemd/system/remote-agent.service
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

    # Enable and start service
    sudo systemctl daemon-reload
    sudo systemctl enable remote-agent
    sudo systemctl start remote-agent
    
    echo "✅ Agent installed successfully!"
    echo ""
    echo "Commands:"
    echo "  Status: sudo systemctl status remote-agent"
    echo "  Logs:   sudo journalctl -u remote-agent -f"
    echo "  Stop:   sudo systemctl stop remote-agent"
    echo "  Start:  sudo systemctl start remote-agent"
else
    # macOS - create launchd plist instead
    mkdir -p "$HOME/Library/LaunchAgents"
    PLIST_FILE="$HOME/Library/LaunchAgents/com.remote-agent.plist"
    
    cat << EOF > $PLIST_FILE
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
    <key>NetworkState</key>
    <true/>
</dict>
</plist>
EOF
    
    # Load the service
    launchctl load $PLIST_FILE
    
    echo "✅ Agent installed successfully!"
    echo ""
    echo "Commands:"
    echo "  Status: launchctl list | grep remote-agent"
    echo "  Logs:   tail -f $INSTALL_DIR/agent.log"
    echo "  Stop:   launchctl unload $PLIST_FILE"
    echo "  Start:  launchctl load $PLIST_FILE"
fi
