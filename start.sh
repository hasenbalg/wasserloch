#!/bin/bash
#
# Garden Watering System - Startup Script
# Starts the WiFi access point and web server
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "  Garden Watering System Startup"
echo "========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./start.sh)"
    exit 1
fi

# Install dependencies if needed
echo "Checking dependencies..."
pip3 list 2>/dev/null | grep -q Flask || pip3 install flask
pip3 list 2>/dev/null | grep -q RPi.GPIO || pip3 install RPi.GPIO

# Create required directories
mkdir -p /etc/hostapd
mkdir -p /etc/dnsmasq.d

# Install hostapd and dnsmasq if not present
dpkg -l | grep -q hostapd || apt-get install -y hostapd dnsmasq
dpkg -l | grep -q python3-flask || pip3 install flask

# Check if wlan0 exists
if ! ip link show wlan0 &>/dev/null; then
    echo "ERROR: wlan0 interface not found!"
    echo "Make sure your Raspberry Pi has a WiFi adapter."
    exit 1
fi

# Stop any running instances
pkill -f "python3 app.py" 2>/dev/null || true
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

# Start Access Point mode
echo "Starting Access Point mode..."
python3 wifi_manager.py start_ap 2>/dev/null || {
    echo "Attempting to start AP manually..."
    
    # Stop NetworkManager
    systemctl stop NetworkManager 2>/dev/null || true
    systemctl stop wpa_supplicant 2>/dev/null || true
    
    # Configure hostapd
    cat > /etc/hostapd/hostapd.conf << 'EOF'
interface=wlan0
driver=nl80211
ssid=Garden-Watering
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=watering123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

    # Configure dnsmasq
    cat > /etc/dnsmasq.d/garden.conf << 'EOF'
interface=wlan0
dhcp-range=192.168.4.100,192.168.4.250,255.255.255.0,12h
EOF

    # Configure wlan0 with static IP
    ip addr flush dev wlan0
    ip addr add 192.168.4.1/24 dev wlan0
    ip link set wlan0 up
    
    # Start services
    systemctl start hostapd
    systemctl start dnsmasq
    
    echo "Access Point started: Garden-Watering (watering123)"
}

echo ""
echo "========================================="
echo "  System Ready!"
echo "========================================="
echo ""
echo "Connect to WiFi: Garden-Watering"
echo "Password: watering123"
echo ""
echo "Access web interface at: http://192.168.4.1"
echo ""
echo "To switch to your home WiFi:"
echo "  1. Open http://192.168.4.1/wifi"
echo "  2. Enter your network credentials"
echo "  3. The system will reconnect automatically"
echo ""
echo "Starting web server..."
echo ""

# Start the Flask application
exec python3 app.py
