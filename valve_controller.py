"""
Valve Controller Module
Handles GPIO control for 4 water valves.
Only one valve can be open at any time.
"""

import RPi.GPIO as GPIO
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Valve GPIO pins (adjust based on your wiring)
VALVE_PINS = [17, 27, 22, 24]  # GPIO 17, 27, 22, 24 for valves 1-4
VALVE_COUNT = len(VALVE_PINS)

# State tracking
_active_valve = None
_active_valve_lock = threading.Lock()
_valve_timers = {}  # valve_id -> timer thread


class ValveController:
    """Controls water valves with mutual exclusion."""

    def __init__(self, use_gpio=True):
        self.use_gpio = use_gpio
        self._initialize_gpio()

    def _initialize_gpio(self):
        """Initialize GPIO pins."""
        if self.use_gpio:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for pin in VALVE_PINS:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)  # Start with all valves closed
            logger.info("GPIO initialized for %d valves", VALVE_COUNT)
        else:
            logger.info("GPIO simulation mode enabled")

    def get_valve_count(self):
        """Return the number of valves."""
        return VALVE_COUNT

    def get_valve_pins(self):
        """Return list of valve GPIO pins."""
        return VALVE_PINS.copy()

    def _open_valve_gpio(self, valve_id):
        """Open a valve via GPIO."""
        if 0 <= valve_id < VALVE_COUNT:
            pin = VALVE_PINS[valve_id]
            GPIO.output(pin, GPIO.HIGH)
            logger.info("Valve %d opened (GPIO pin %d)", valve_id + 1, pin)

    def _close_valve_gpio(self, valve_id):
        """Close a valve via GPIO."""
        if 0 <= valve_id < VALVE_COUNT:
            pin = VALVE_PINS[valve_id]
            GPIO.output(pin, GPIO.LOW)
            logger.info("Valve %d closed (GPIO pin %d)", valve_id + 1, pin)

    def get_currently_open_valve(self):
        """Get the currently open valve ID, or None."""
        with _active_valve_lock:
            return _active_valve

    def open_valve(self, valve_id, duration_seconds=None):
        """
        Open a valve. Only one valve can be open at a time.
        
        Args:
            valve_id: 0-based valve ID (0-3)
            duration_seconds: Optional duration in seconds. None = manual close.
        
        Returns:
            dict with status and message
        """
        # Validate valve_id
        if not isinstance(valve_id, int) or valve_id < 0 or valve_id >= VALVE_COUNT:
            return {"success": False, "message": f"Invalid valve ID. Must be 0-{VALVE_COUNT - 1}"}

        # Check if another valve is already open
        with _active_valve_lock:
            if _active_valve is not None:
                return {
                    "success": False,
                    "message": f"Valve {_active_valve + 1} is already open. Close it first."
                }

            # Open the requested valve
            _active_valve = valve_id

        if self.use_gpio:
            self._open_valve_gpio(valve_id)

        # Handle automatic close with timer
        if duration_seconds is not None:
            timer = threading.Timer(duration_seconds, self._close_valve_callback, [valve_id])
            timer.daemon = True
            timer.start()
            _valve_timers[valve_id] = timer
            duration_minutes = duration_seconds / 60
            return {
                "success": True,
                "valve_id": valve_id,
                "message": f"Valve {valve_id + 1} opened for {duration_minutes:.1f} minutes"
            }

        return {
            "success": True,
            "valve_id": valve_id,
            "message": f"Valve {valve_id + 1} opened (manual close required)"
        }

    def close_valve(self, valve_id=None):
        """
        Close a valve. If no valve_id specified, closes the currently open valve.
        
        Args:
            valve_id: Optional valve ID to close.
        
        Returns:
            dict with status and message
        """
        with _active_valve_lock:
            if _active_valve is None:
                return {"success": False, "message": "No valve is currently open"}

            if valve_id is not None:
                if valve_id != _active_valve:
                    return {
                        "success": False,
                        "message": f"Valve {valve_id + 1} is not open. Valve {_active_valve + 1} is open."
                    }

            valve_to_close = valve_id if valve_id is not None else _active_valve

        if self.use_gpio:
            self._close_valve_gpio(valve_to_close)

        # Cancel any timer for this valve
        with _active_valve_lock:
            if valve_to_close in _valve_timers:
                _valve_timers[valve_to_close].cancel()
                del _valve_timers[valve_to_close]
            _active_valve = None

        logger.info("Valve %d closed", valve_to_close + 1)
        return {"success": True, "message": f"Valve {valve_to_close + 1} closed"}

    def close_all_valves(self):
        """Close all valves (emergency stop)."""
        with _active_valve_lock:
            if _active_valve is not None:
                valve_to_close = _active_valve
                _active_valve = None

            for timer in _valve_timers.values():
                timer.cancel()
            _valve_timers.clear()

        if self.use_gpio and valve_to_close is not None:
            self._close_valve_gpio(valve_to_close)

        logger.info("All valves closed (emergency)")
        return {"success": True, "message": "All valves closed"}

    def _close_valve_callback(self, valve_id):
        """Callback for automatic valve close."""
        self.close_valve(valve_id)

    def cleanup(self):
        """Clean up GPIO resources."""
        if self.use_gpio:
            self.close_all_valves()
            GPIO.cleanup()
            logger.info("GPIO cleanup complete")


# Global instance (initialized with use_gpio=True on Raspberry Pi)
controller = None


def get_controller(use_gpio=None):
    """Get or create the global valve controller instance."""
    global controller
    if controller is None:
        use_gpio = use_gpio if use_gpio is not None else True
        controller = ValveController(use_gpio=use_gpio)
    return controller
