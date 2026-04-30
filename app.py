"""
Garden Watering System - Main Flask Application
Web interface for controlling 4 water valves with scheduling.
"""

import json
import os
import time
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session
from valve_controller import get_controller
from wifi_manager import get_wifi_manager
from schedule_controller import load_schedule, save_schedule
from time_controller import sync_system_time, get_adjusted_time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'garden-watering-secret-key-change-in-production')

# Configuration file paths
SCHEDULE_FILE = "/home/user/garden_watering_system/schedule.json"
SYSTEM_TIME_FILE = "/home/user/garden_watering_system/system_time.json"

# Days of the week
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Payload verification key (shared between frontend and backend)
PAYLOAD_SECRET = os.environ.get('PAYLOAD_SECRET', 'garden-valve-2024')


def verify_payload(data, secret):
    """
    Verify the payload integrity.
    Checks that the payload contains the correct secret hash.
    This prevents unauthorized valve operations.
    """
    if not data or not isinstance(data, dict):
        return False
    
    # Check required fields
    if 'valve_id' not in data or 'timestamp' not in data:
        return False
    
    # Verify valve_id is valid (0-3)
    valve_id = data.get('valve_id')
    if not isinstance(valve_id, int) or valve_id < 0 or valve_id > 3:
        return False
    
    # Verify timestamp is recent (within 5 minutes)
    try:
        ts = int(data['timestamp'])
        if abs(ts - int(time.time())) > 300:  # 5 minutes
            return False
    except (ValueError, TypeError):
        return False
    
    # Verify payload secret hash
    expected_hash = data.get('payload_hash')
    if not expected_hash:
        return False
    
    # Create expected hash from payload contents
    payload_content = json.dumps({
        'valve_id': data['valve_id'],
        'timestamp': data['timestamp'],
        'action': data.get('action', 'open')
    }, sort_keys=True)
    
    import hashlib
    expected = hashlib.sha256((payload_content + secret).encode()).hexdigest()
    
    return expected == expected_hash



# ==================== Routes ====================

@app.route('/')
def index():
    """Main page with watering schedule interface."""
    return render_template('index.html')


@app.route('/wifi')
def wifi_page():
    """WiFi settings page."""
    return render_template('wifi_settings.html')


@app.route('/api/status')
def api_status():
    """Get system status."""
    controller = get_controller(use_gpio=False)  # Use simulation for status check
    valve_status = controller.open_valve(0) if False else {"success": True}
    
    return jsonify({
        "valves": controller.get_valve_count(),
        "currently_open": None,  # Will be updated
        "schedule": load_schedule(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route('/api/valves/available', methods=['GET'])
def get_available_valves():
    """Get list of available valves."""
    controller = get_controller(use_gpio=False)
    return jsonify({
        "valves": list(range(controller.get_valve_count())),
        "count": controller.get_valve_count()
    })


@app.route('/api/valve/open', methods=['POST'])
def open_valve():
    """
    Open a valve with payload verification.
    Requires: valve_id (0-3), timestamp, payload_hash
    Only one valve can be open at a time.
    """
    data = request.get_json()
    
    # Verify payload integrity
    if not verify_payload(data, PAYLOAD_SECRET):
        logger.warning("Invalid payload rejected: %s", data)
        return jsonify({
            "success": False,
            "message": "Invalid or tampered request. Payload verification failed."
        }), 403
    
    controller = get_controller()
    result = controller.open_valve(data['valve_id'])
    
    return jsonify(result)


@app.route('/api/valve/close', methods=['POST'])
def close_valve():
    """Close a valve with payload verification."""
    data = request.get_json()
    
    if not verify_payload(data, PAYLOAD_SECRET):
        return jsonify({
            "success": False,
            "message": "Invalid or tampered request."
        }), 403
    
    controller = get_controller()
    valve_id = data.get('valve_id')
    result = controller.close_valve(valve_id)
    
    return jsonify(result)


@app.route('/api/valve/stop-all', methods=['POST'])
def stop_all_valves():
    """Emergency stop - close all valves with payload verification."""
    data = request.get_json()
    
    if not verify_payload(data, PAYLOAD_SECRET):
        return jsonify({
            "success": False,
            "message": "Invalid or tampered request."
        }), 403
    
    controller = get_controller()
    result = controller.close_all_valves()
    
    return jsonify(result)


@app.route('/api/schedule', methods=['GET'])
def get_schedule():
    """Get the current watering schedule."""
    schedule = load_schedule()
    return jsonify({"schedule": schedule})


@app.route('/api/schedule', methods=['POST'])
def set_schedule():
    """Set the watering schedule."""
    data = request.get_json()
    
    if not data or 'schedule' not in data:
        return jsonify({"success": False, "message": "Invalid schedule data"}), 400
    
    schedule = data['schedule']
    
    # Validate schedule
    for day in DAYS:
        if day not in schedule:
            return jsonify({"success": False, "message": f"Missing day: {day}"}), 400
        
        slots = schedule[day]
        if not isinstance(slots, list):
            return jsonify({"success": False, "message": f"Invalid slots for {day}"}), 400
        
        for slot in slots:
            if not all(k in slot for k in ['start_time', 'duration_minutes', 'valve_id']):
                return jsonify({"success": False, "message": f"Invalid slot format for {day}"}), 400
            
            # Validate valve_id
            if not isinstance(slot['valve_id'], int) or slot['valve_id'] < 0 or slot['valve_id'] > 3:
                return jsonify({"success": False, "message": f"Invalid valve_id in {day} slot"}), 400
            
            # Validate duration
            if not isinstance(slot['duration_minutes'], (int, float)) or slot['duration_minutes'] <= 0:
                return jsonify({"success": False, "message": f"Invalid duration in {day} slot"}), 400
    
    save_schedule(schedule)
    return jsonify({"success": True, "message": "Schedule saved"})


@app.route('/api/time/sync', methods=['POST'])
def sync_time():
    """Synchronize system time with browser clock."""
    data = request.get_json()
    if not data or 'timestamp' not in data:
        return jsonify({"success": False, "message": "Missing timestamp"}), 400
    
    result = sync_system_time(data['timestamp'])
    return jsonify(result)


@app.route('/api/time/current', methods=['GET'])
def get_current_time():
    """Get current system time."""
    return jsonify({
        "timestamp": int(time.time()),
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "Local"
    })


# ==================== WiFi Routes ====================

@app.route('/api/wifi/status', methods=['GET'])
def wifi_status():
    """Get WiFi status."""
    wifi = get_wifi_manager()
    return jsonify(wifi.get_status())


@app.route('/api/wifi/scan', methods=['GET'])
def scan_networks():
    """Scan for available WiFi networks."""
    wifi = get_wifi_manager()
    networks = wifi.get_available_networks()
    return jsonify({"networks": networks})


@app.route('/api/wifi/connect', methods=['POST'])
def connect_network():
    """Connect to a WiFi network."""
    data = request.get_json()
    if not data or 'ssid' not in data or 'password' not in data:
        return jsonify({"success": False, "message": "Missing ssid or password"}), 400
    
    wifi = get_wifi_manager()
    result = wifi.connect_to_network(data['ssid'], data['password'])
    return jsonify(result)


@app.route('/api/wifi/ap', methods=['POST'])
def start_ap_mode():
    """Start Access Point mode."""
    wifi = get_wifi_manager()
    result = wifi.start_ap()
    return jsonify(result)


@app.route('/api/wifi/credentials', methods=['POST'])
def update_ap_credentials():
    """Update AP SSID and password."""
    data = request.get_json()
    if not data or 'ssid' not in data or 'password' not in data:
        return jsonify({"success": False, "message": "Missing ssid or password"}), 400
    
    wifi = get_wifi_manager()
    result = wifi.set_ap_credentials(data['ssid'], data['password'])
    return jsonify(result)


# ==================== Main ====================

if __name__ == '__main__':
    # Initialize controllers
    controller = get_controller(use_gpio=False)  # Use simulation for development
    wifi = get_wifi_manager()
    
    # Initialize schedule file if not exists
    if not os.path.exists(SCHEDULE_FILE):
        save_schedule({day: [] for day in DAYS})
    
    # Get WiFi status
    wifi_status_data = wifi.get_status()
    print(f"WiFi Mode: {wifi_status_data['mode']}")
    
    # Determine bind address based on WiFi mode
    if wifi_status_data['mode'] == 'ap':
        host = '0.0.0.0'
        port = 80
    else:
        host = '0.0.0.0'
        port = 8080
    
    print(f"Server starting on {host}:{port}")
    print("Access the web interface:")
    if wifi_status_data['mode'] == 'ap':
        print(f"  http://192.168.4.1")
    else:
        print(f"  Use your Pi's IP address on port {port}")
    
    app.run(host=host, port=port, debug=True)
