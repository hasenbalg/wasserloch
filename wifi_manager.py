"""
WiFi Manager Module
Manages WiFi in Access Point mode and allows connecting to existing networks.
"""

import subprocess
import json
import os
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONFIG_FILE = "/home/user/garden_watering_system/wifi_config.json"
WPA_SUPPLICANT_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"
HOSTAPD_CONF = "/etc/hostapd/hostapd.conf"


class WiFiManager:
    """Manages WiFi AP mode and station connections."""

    AP_SSID = "Garden-Watering"
    AP_PASSWORD = "watering123"
    AP_CHANNEL = 6
    AP_IP = "192.168.4.1"
    AP_NETMASK = "255.255.255.0"
    AP_GATEWAY = "192.168.4.1"

    def __init__(self):
        self.config = self._load_config()
        self.current_mode = self._detect_mode()

    def _load_config(self):
        """Load WiFi configuration from file."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load config: %s", e)
        return {"mode": "ap", "saved_networks": []}

    def _save_config(self):
        """Save WiFi configuration to file."""
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=2)
        logger.info("WiFi config saved")

    def _detect_mode(self):
        """Detect current WiFi mode."""
        try:
            result = subprocess.run(
                ["iwgetid", "-r"], capture_output=True, text=True, timeout=5
            )
            ssid = result.stdout.strip()
            if ssid == self.AP_SSID:
                return "ap"
            elif ssid:
                return "station"
            else:
                return "ap"  # Default to AP mode
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "ap"

    def get_status(self):
        """Get current WiFi status."""
        status = {
            "mode": self.current_mode,
            "ssid": None,
            "ip": None,
            "saved_networks": self.config.get("saved_networks", [])
        }

        try:
            # Get current SSID
            result = subprocess.run(
                ["iwgetid", "-r"], capture_output=True, text=True, timeout=5
            )
            status["ssid"] = result.stdout.strip() or None

            # Get IP address
            result = subprocess.run(
                ["hostname", "-I"], capture_output=True, text=True, timeout=5
            )
            status["ip"] = result.stdout.strip().split()[0] if result.stdout.strip() else None
        except Exception as e:
            logger.warning("Failed to get WiFi status: %s", e)

        return status

    def start_ap(self):
        """Start Access Point mode."""
        logger.info("Starting AP mode...")
        
        # Stop wpa_supplicant if running
        subprocess.run(["sudo", "systemctl", "stop", "wpa_supplicant.service"],
                      capture_output=True)
        
        # Stop NetworkManager for clean AP start
        subprocess.run(["sudo", "systemctl", "stop", "NetworkManager.service"],
                      capture_output=True)

        # Create hostapd config
        self._create_hostapd_config()

        # Configure interface for AP
        self._configure_ap_interface()

        # Start hostapd
        subprocess.run(["sudo", "systemctl", "start", "hostapd.service"],
                      capture_output=True)

        # Start DHCP server (dnsmasq)
        self._start_dhcp()

        self.config["mode"] = "ap"
        self.current_mode = "ap"
        self._save_config()

        return {"success": True, "message": "AP mode started", "ip": self.AP_IP}

    def stop_ap(self):
        """Stop Access Point mode."""
        logger.info("Stopping AP mode...")
        
        subprocess.run(["sudo", "systemctl", "stop", "hostapd.service"],
                      capture_output=True)
        subprocess.run(["sudo", "systemctl", "stop", "dnsmasq.service"],
                      capture_output=True)
        
        # Restore networking
        subprocess.run(["sudo", "systemctl", "start", "NetworkManager.service"],
                      capture_output=True)
        subprocess.run(["sudo", "systemctl", "start", "wpa_supplicant.service"],
                      capture_output=True)

    def connect_to_network(self, ssid, password):
        """Connect to a WiFi network."""
        logger.info("Connecting to network: %s", ssid)

        # Stop AP mode first
        self.stop_ap()

        # Add network to wpa_supplicant
        self._add_wpa_network(ssid, password)

        # Connect using NetworkManager
        result = subprocess.run(
            ["sudo", "nmcli", "device", "wifi", "connect", ssid, "password", password],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            self.config["mode"] = "station"
            self.config["saved_networks"] = self._get_saved_networks()
            self.current_mode = "station"
            self._save_config()
            
            return {
                "success": True,
                "message": f"Connected to {ssid}",
                "ssid": ssid
            }
        else:
            # Fallback: restart wpa_supplicant
            subprocess.run(["sudo", "systemctl", "restart", "wpa_supplicant.service"],
                          capture_output=True)
            return {
                "success": False,
                "message": f"Failed to connect: {result.stderr.strip()}"
            }

    def _create_hostapd_config(self):
        """Create hostapd configuration file."""
        config = f"""interface=wlan0
driver=nl80211
ssid={self.AP_SSID}
hw_mode=g
channel={self.AP_CHANNEL}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={self.AP_PASSWORD}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
        with open(HOSTAPD_CONF, 'w') as f:
            f.write(config)
        logger.info("Hostapd config created")

    def _configure_ap_interface(self):
        """Configure wlan0 interface for AP mode."""
        # Set static IP
        subprocess.run(
            ["sudo", "ip", "addr", "flush", "dev", "wlan0"],
            capture_output=True
        )
        subprocess.run(
            ["sudo", "ip", "addr", "add", f"{self.AP_IP}/24", "dev", "wlan0"],
            capture_output=True
        )
        subprocess.run(
            ["sudo", "ip", "link", "set", "wlan0", "up"],
            capture_output=True
        )

    def _start_dhcp(self):
        """Start dnsmasq for DHCP in AP mode."""
        os.makedirs("/etc/dnsmasq.d", exist_ok=True)
        config = f"""interface=wlan0
dhcp-range={self.AP_IP.lstrip('.')[:-1]}.100,{self.AP_IP.lstrip('.')[:-1]}.250,255.255.255.0,12h
"""
        with open("/etc/dnsmasq.d/garden.conf", 'w') as f:
            f.write(config)
        
        subprocess.run(["sudo", "systemctl", "restart", "dnsmasq.service"],
                      capture_output=True)

    def _add_wpa_network(self, ssid, password):
        """Add a network to wpa_supplicant configuration."""
        # Generate PSK
        psk_result = subprocess.run(
            ["wpa_passphrase", ssid, password],
            capture_output=True, text=True
        )
        
        if os.path.exists(WPA_SUPPLICANT_CONF):
            with open(WPA_SUPPLICANT_CONF, 'r') as f:
                current_config = f.read()
        else:
            current_config = ""

        # Remove existing network block for this SSID
        pattern = rf'network=\{{[^}}]*ssid="{re.escape(ssid)}"[^}}]*\}}'
        current_config = re.sub(pattern, '', current_config, flags=re.DOTALL)

        # Add new network block
        new_block = psk_result.stdout.strip()
        full_config = current_config + "\n" + new_block + "\n"

        with open(WPA_SUPPLICANT_CONF, 'w') as f:
            f.write(full_config)

    def _get_saved_networks(self):
        """Get list of saved network SSIDs."""
        networks = []
        if os.path.exists(WPA_SUPPLICANT_CONF):
            try:
                with open(WPA_SUPPLICANT_CONF, 'r') as f:
                    content = f.read()
                # Extract SSIDs from network blocks
                pattern = r'ssid="([^"]+)"'
                networks = list(set(re.findall(pattern, content)))
            except IOError:
                pass
        return networks

    def set_ap_credentials(self, ssid, password):
        """Update AP SSID and password."""
        if len(password) < 8:
            return {"success": False, "message": "Password must be at least 8 characters"}
        
        self.AP_SSID = ssid
        self.AP_PASSWORD = password
        return {"success": True, "message": "AP credentials updated"}

    def switch_to_ap(self):
        """Switch to AP mode."""
        return self.start_ap()

    def switch_to_station(self, ssid, password):
        """Switch to station mode by connecting to a network."""
        return self.connect_to_network(ssid, password)

    def get_available_networks(self):
        """Scan for available WiFi networks."""
        try:
            result = subprocess.run(
                ["sudo", "nmcli", "-t", "-f", "SSID,SECURITY,signal", "device", "wifi", "list"],
                capture_output=True, text=True, timeout=15
            )
            networks = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split(':')
                    if len(parts) >= 3:
                        ssid = parts[0] if parts[0] else f"Hidden ({parts[2]}dBm)"
                        networks.append({
                            "ssid": ssid,
                            "security": parts[1],
                            "signal": parts[2]
                        })
            return networks
        except Exception as e:
            logger.warning("Failed to scan networks: %s", e)
            return []


# Global instance
wifi_manager = None


def get_wifi_manager():
    """Get or create the global WiFi manager instance."""
    global wifi_manager
    if wifi_manager is None:
        wifi_manager = WiFiManager()
    return wifi_manager
