# 🌱 Garden Watering System

A Raspberry Pi-based automated garden watering system with web interface, scheduling, and WiFi management.

## Features

- **4 Water Valves** - Control up to 4 independent watering zones
- **Weekly Scheduling** - Set multiple time slots for each day of the week
- **Mutual Exclusion** - Only one valve can be open at any time (enforced on both frontend and backend)
- **Payload Verification** - SHA-256 hash verification prevents unauthorized valve operations
- **Clock Synchronization** - System time syncs with browser clock on each connection
- **Access Point Mode** - Starts in AP mode for easy configuration
- **WiFi Management** - Connect to existing networks via web interface

## Hardware Requirements

- Raspberry Pi (3, 4, or Zero W recommended)
- WiFi adapter (built-in on most Pi models)
- 4-channel relay module
- 4 water valves (solenoid valves)
- 5V power supply for relay module

## Wiring Diagram

```
Raspberry Pi          Relay Module          Water Valves
==============          ============          =============
GPIO 17  ──────────>  IN1  ──────────>  Valve 1 (Zone A)
GPIO 27  ──────────>  IN2  ──────────>  Valve 2 (Zone B)
GPIO 22  ──────────>  IN3  ──────────>  Valve 3 (Zone C)
GPIO 24  ──────────>  IN4  ──────────>  Valve 4 (Zone D)
5V       ──────────>  VCC
GND      ──────────>  GND
```

## Installation

### 1. Clone or copy the project

```bash
cd /home/user
git clone <repository-url> garden_watering_system
# OR copy the files to /home/user/garden_watering_system
```

### 2. Install dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev hostapd dnsmasq
cd garden_watering_system
pip3 install flask
```

### 3. Make startup script executable

```bash
chmod +x start.sh
```

### 4. Configure GPIO pins (if different from defaults)

Edit `valve_controller.py` and modify `VALVE_PINS`:

```python
VALVE_PINS = [17, 27, 22, 24]  # Change to your wiring
```

### 5. Set up auto-start (optional)

```bash
sudo cp start.sh /usr/local/bin/garden-watering
sudo tee /etc/systemd/system/garden-watering.service << 'EOF'
[Unit]
Description=Garden Watering System
After=network.target

[Service]
ExecStart=/bin/bash /usr/local/bin/garden-watering
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable garden-watering
sudo systemctl start garden-watering
```

## Usage

### Initial Setup

1. **Power on** the Raspberry Pi
2. **Connect** to WiFi: `Garden-Watering` (password: `watering123`)
3. **Open browser** and go to: `http://192.168.4.1`

### Connecting to Home WiFi

1. Navigate to **WiFi Settings** tab
2. Enter your home network SSID and password
3. Click **Connect**
4. The Pi will reconnect to your network
5. Access the web interface using your Pi's new IP address

### Scheduling Watering

1. Go to the **Schedule** tab
2. Click **+** on any day to add a watering slot
3. Set:
   - **Time** - When watering starts
   - **Valve** - Which zone to water
   - **Duration** - How long (1-120 minutes)
4. Click **Save Schedule**

### Manual Control

- Click **Open** on any valve card to water manually
- Set the duration or close manually with **Close**
- Use **Stop All Valves** for emergency shutdown

## Security Features

### Payload Verification

All valve operations require a cryptographically signed payload:

1. **Frontend verification** - JavaScript validates valve_id (0-3), timestamp (within 5 minutes), and generates SHA-256 hash
2. **Backend verification** - Flask server verifies the hash matches expected value
3. **Replay protection** - Timestamps older than 5 minutes are rejected

```javascript
// Example payload structure
{
    "valve_id": 0,
    "timestamp": 1704067200,
    "action": "open",
    "payload_hash": "a1b2c3d4..."  // SHA-256 hash
}
```

### Clock Synchronization

- System time syncs with browser clock on each page load
- Time difference is stored and used for accurate scheduling
- Warning shown if difference exceeds 5 minutes (suggests NTP sync needed)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Get system status |
| GET | `/api/valves/available` | List available valves |
| POST | `/api/valve/open` | Open a valve (requires payload) |
| POST | `/api/valve/close` | Close a valve (requires payload) |
| POST | `/api/valve/stop-all` | Emergency stop all valves |
| GET | `/api/schedule` | Get watering schedule |
| POST | `/api/schedule` | Save watering schedule |
| POST | `/api/time/sync` | Sync system time with browser |
| GET | `/api/wifi/status` | Get WiFi status |
| GET | `/api/wifi/scan` | Scan for networks |
| POST | `/api/wifi/connect` | Connect to network |
| POST | `/api/wifi/ap` | Start AP mode |

## Configuration

### Change AP Credentials

Edit `wifi_manager.py`:

```python
AP_SSID = "Garden-Watering"
AP_PASSWORD = "watering123"
```

Or use the web interface in WiFi Settings.

### Change Payload Secret

Edit `app.py` and modify `PAYLOAD_SECRET`:

```python
PAYLOAD_SECRET = 'your-secure-random-string'
```

Also update `script.js`:

```javascript
const PAYLOAD_SECRET = 'your-secure-random-string';
```

## Troubleshooting

### WiFi Issues

```bash
# Check WiFi status
iwgetid -r

# Restart networking
sudo systemctl restart NetworkManager
sudo systemctl restart hostapd
```

### GPIO Not Working

- Ensure relay module is properly connected
- Check GPIO pin numbers in `valve_controller.py`
- Run as root or add user to gpio group: `sudo usermod -aG gpio $USER`

### Time Sync Issues

```bash
# Install and configure NTP
sudo apt-get install -y chrony
sudo systemctl enable chrony
sudo systemctl start chrony
```

### Flask Not Starting

```bash
# Check for port conflicts
sudo lsof -i :80
sudo lsof -i :8080

# Install Flask
pip3 install flask
```

## File Structure

```
garden_watering_system/
├── app.py                  # Flask web server
├── valve_controller.py     # GPIO valve control
├── wifi_manager.py         # WiFi AP/station management
├── start.sh                # Startup script
├── README.md               # This file
├── schedule.json           # Saved schedule data
├── wifi_config.json        # WiFi configuration
├── system_time.json        # Time sync data
├── templates/
│   ├── index.html          # Main schedule page
│   └── wifi_settings.html  # WiFi configuration page
└── static/
    ├── style.css           # Styles
    └── script.js           # Frontend JavaScript
```

## Run Tests
```bash
cd /home/user/garden_watering_system
python3 -m unittest test_valve_controller -v
```

## License

MIT License - Feel free to modify and use for your garden!
