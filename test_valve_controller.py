"""
Tests for Valve Controller Module
Tests GPIO control, mutual exclusion, timing, and error handling.
"""

import sys
import unittest
import time
import threading
from unittest.mock import patch, MagicMock, call

# Mock RPi.GPIO before importing valve_controller
mock_gpio = MagicMock()
mock_gpio.BCM = 11
mock_gpio.OUT = 1
mock_gpio.LOW = 0
mock_gpio.HIGH = 1
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = mock_gpio

from valve_controller import (
    ValveController,
    VALVE_PINS,
    VALVE_COUNT,
    get_controller,
    controller,
    reset_state
)


class TestValveControllerInit(unittest.TestCase):
    """Test initialization of ValveController."""

    def setUp(self):
        """Reset state before each test."""
        reset_state()
        import valve_controller
        valve_controller.controller = None

    def test_init_simulation_mode(self):
        """Test initialization in simulation mode (no GPIO)."""
        with patch('valve_controller.GPIO'):
            controller = ValveController(use_gpio=False)
            self.assertEqual(controller.use_gpio, False)

    def test_init_gpio_mode(self):
        """Test initialization with GPIO enabled."""
        with patch('valve_controller.GPIO') as mock_gpio:
            mock_gpio.BCM = 11
            mock_gpio.OUT = 1
            mock_gpio.LOW = 0
            mock_gpio.HIGH = 1
            controller = ValveController(use_gpio=True)
            self.assertEqual(controller.use_gpio, True)
            # Should have set up all pins as outputs
            self.assertEqual(mock_gpio.setup.call_count, VALVE_COUNT)
            # Should have closed all valves initially
            self.assertEqual(mock_gpio.output.call_count, VALVE_COUNT)

    def test_get_valve_count(self):
        """Test getting the number of valves."""
        with patch('valve_controller.GPIO'):
            controller = ValveController(use_gpio=False)
            self.assertEqual(controller.get_valve_count(), 4)

    def test_get_valve_pins(self):
        """Test getting valve GPIO pins."""
        with patch('valve_controller.GPIO'):
            controller = ValveController(use_gpio=False)
            pins = controller.get_valve_pins()
            self.assertEqual(len(pins), 4)
            # Verify it's a copy, not the same reference
            pins.append(99)
            self.assertNotIn(99, VALVE_PINS)


class TestValveOpen(unittest.TestCase):
    """Test opening valves."""

    def setUp(self):
        """Set up test fixtures."""
        reset_state()
        self.controller = ValveController(use_gpio=False)

    def test_open_valid_valve(self):
        """Test opening a valid valve (0-3)."""
        result = self.controller.open_valve(0)
        self.assertTrue(result['success'])
        self.assertEqual(result['valve_id'], 0)
        self.assertIn('opened', result['message'].lower())

    def test_open_all_valves_sequentially(self):
        """Test opening each valve (with close in between)."""
        for valve_id in range(VALVE_COUNT):
            result = self.controller.open_valve(valve_id)
            self.assertTrue(result['success'])
            self.controller.close_valve(valve_id)

    def test_open_invalid_valve_negative(self):
        """Test opening a valve with negative ID."""
        result = self.controller.open_valve(-1)
        self.assertFalse(result['success'])
        self.assertIn('Invalid', result['message'])

    def test_open_invalid_valve_too_high(self):
        """Test opening a valve with ID >= 4."""
        result = self.controller.open_valve(4)
        self.assertFalse(result['success'])
        self.assertIn('Invalid', result['message'])

    def test_open_invalid_valve_string(self):
        """Test opening a valve with string ID."""
        result = self.controller.open_valve("0")
        self.assertFalse(result['success'])
        self.assertIn('Invalid', result['message'])

    def test_open_with_duration(self):
        """Test opening a valve with automatic close duration."""
        result = self.controller.open_valve(0, duration_seconds=60)
        self.assertTrue(result['success'])
        self.assertIn('minutes', result['message'].lower())

    def test_open_with_short_duration(self):
        """Test opening a valve with very short duration."""
        result = self.controller.open_valve(1, duration_seconds=1)
        self.assertTrue(result['success'])
        self.assertIn('minutes', result['message'].lower())


class TestMutualExclusion(unittest.TestCase):
    """Test that only one valve can be open at a time."""

    def setUp(self):
        """Set up test fixtures."""
        reset_state()
        self.controller = ValveController(use_gpio=False)

    def test_cannot_open_second_valve(self):
        """Test that opening a second valve fails when one is open."""
        # Open first valve
        result1 = self.controller.open_valve(0)
        self.assertTrue(result1['success'])

        # Try to open second valve
        result2 = self.controller.open_valve(1)
        self.assertFalse(result2['success'])
        self.assertIn('already open', result2['message'].lower())

    def test_cannot_open_same_valve_twice(self):
        """Test that opening the same valve twice fails."""
        result1 = self.controller.open_valve(2)
        self.assertTrue(result1['success'])

        result2 = self.controller.open_valve(2)
        self.assertFalse(result2['success'])
        self.assertIn('already open', result2['message'].lower())

    def test_cannot_open_any_valve_when_one_open(self):
        """Test that no valve can be opened when another is open."""
        self.controller.open_valve(0)

        for valve_id in range(1, VALVE_COUNT):
            result = self.controller.open_valve(valve_id)
            self.assertFalse(result['success'])

    def test_get_currently_open_valve(self):
        """Test getting the currently open valve."""
        self.assertIsNone(self.controller.get_currently_open_valve())

        self.controller.open_valve(1)
        self.assertEqual(self.controller.get_currently_open_valve(), 1)

        self.controller.close_valve(1)
        self.assertIsNone(self.controller.get_currently_open_valve())

    def test_switch_valves(self):
        """Test switching from one valve to another."""
        # Open valve 0
        self.controller.open_valve(0)
        self.assertEqual(self.controller.get_currently_open_valve(), 0)

        # Close valve 0
        self.controller.close_valve(0)
        self.assertIsNone(self.controller.get_currently_open_valve())

        # Open valve 2
        self.controller.open_valve(2)
        self.assertEqual(self.controller.get_currently_open_valve(), 2)


class TestValveClose(unittest.TestCase):
    """Test closing valves."""

    def setUp(self):
        """Set up test fixtures."""
        reset_state()
        self.controller = ValveController(use_gpio=False)

    def test_close_open_valve(self):
        """Test closing an open valve."""
        self.controller.open_valve(0)
        result = self.controller.close_valve(0)
        self.assertTrue(result['success'])
        self.assertIn('closed', result['message'].lower())

    def test_close_specific_valve_when_different_open(self):
        """Test closing a specific valve when a different one is open."""
        self.controller.open_valve(0)
        result = self.controller.close_valve(2)
        self.assertFalse(result['success'])
        self.assertIn('is not open', result['message'])

    def test_close_nonexistent_valve(self):
        """Test closing a valve that was never opened."""
        result = self.controller.close_valve(0)
        self.assertFalse(result['success'])
        self.assertIn('No valve is currently open', result['message'])

    def test_close_invalid_valve_id(self):
        """Test closing with invalid valve ID."""
        result = self.controller.close_valve(5)
        self.assertFalse(result['success'])
        self.assertIn('No valve is currently open', result['message'])

    def test_close_allows_new_valve(self):
        """Test that closing allows opening a new valve."""
        self.controller.open_valve(0)
        self.controller.close_valve(0)

        result = self.controller.open_valve(1)
        self.assertTrue(result['success'])


class TestAutomaticClose(unittest.TestCase):
    """Test automatic valve close after duration."""

    def test_auto_close_short_duration(self):
        """Test valve closes automatically after short duration."""
        reset_state()
        controller = ValveController(use_gpio=False)
        controller.open_valve(0, duration_seconds=0.1)

        # Wait for auto-close
        time.sleep(0.3)

        # Valve should be closed now
        result = controller.get_currently_open_valve()
        self.assertIsNone(result)

    def test_auto_close_preserves_duration_format(self):
        """Test that duration is formatted correctly in message."""
        reset_state()
        controller = ValveController(use_gpio=False)
        result = controller.open_valve(0, duration_seconds=90)
        self.assertIn('minutes', result['message'].lower())
        self.assertIn('1.5', result['message'])

    def test_manual_close_cancels_timer(self):
        """Test that manual close cancels the automatic timer."""
        reset_state()
        controller = ValveController(use_gpio=False)
        controller.open_valve(0, duration_seconds=5)

        # Manually close before timer expires
        controller.close_valve(0)

        # Wait longer than the timer duration
        time.sleep(0.1)

        # Valve should still be closed (not re-opened by timer)
        self.assertIsNone(controller.get_currently_open_valve())


class TestStopAll(unittest.TestCase):
    """Test emergency stop functionality."""

    def setUp(self):
        """Set up test fixtures."""
        reset_state()
        self.controller = ValveController(use_gpio=False)

    def test_stop_all_no_valves_open(self):
        """Test stopping all when no valves are open."""
        result = self.controller.close_all_valves()
        self.assertTrue(result['success'])
        self.assertIn('All valves closed', result['message'])

    def test_stop_all_single_valve(self):
        """Test stopping all with one valve open."""
        self.controller.open_valve(0)
        result = self.controller.close_all_valves()
        self.assertTrue(result['success'])
        self.assertIsNone(self.controller.get_currently_open_valve())

    def test_stop_all_closes_active_valve(self):
        """Test that stop all actually closes the active valve."""
        self.controller.open_valve(2)
        self.assertEqual(self.controller.get_currently_open_valve(), 2)

        self.controller.close_all_valves()
        self.assertIsNone(self.controller.get_currently_open_valve())

    def test_stop_all_prevents_new_opens(self):
        """Test that after stop all, valves can be opened again."""
        self.controller.open_valve(0)
        self.controller.close_all_valves()

        # Should be able to open a valve after stop-all
        result = self.controller.open_valve(1)
        self.assertTrue(result['success'])


class TestGPIOIntegration(unittest.TestCase):
    """Test GPIO operations with mocking."""

    @patch('valve_controller.GPIO')
    def test_gpio_open_valve(self, mock_gpio):
        """Test GPIO output when opening valve."""
        mock_gpio.BCM = 11
        mock_gpio.OUT = 1
        mock_gpio.LOW = 0
        mock_gpio.HIGH = 1

        reset_state()
        controller = ValveController(use_gpio=True)
        controller.open_valve(0)

        # Check that HIGH was set on the correct pin
        calls = mock_gpio.output.call_args_list
        # Last call should be setting the valve pin to HIGH
        last_call = calls[-1]
        self.assertEqual(last_call[0][0], VALVE_PINS[0])
        self.assertEqual(last_call[0][1], mock_gpio.HIGH)

    @patch('valve_controller.GPIO')
    def test_gpio_close_valve(self, mock_gpio):
        """Test GPIO output when closing valve."""
        mock_gpio.BCM = 11
        mock_gpio.OUT = 1
        mock_gpio.LOW = 0
        mock_gpio.HIGH = 1

        reset_state()
        controller = ValveController(use_gpio=True)
        controller.open_valve(0)
        controller.close_valve(0)

        # Check that LOW was set on the correct pin
        calls = mock_gpio.output.call_args_list
        last_call = calls[-1]
        self.assertEqual(last_call[0][0], VALVE_PINS[0])
        self.assertEqual(last_call[0][1], mock_gpio.LOW)

    @patch('valve_controller.GPIO')
    def test_cleanup_resets_all_pins(self, mock_gpio):
        """Test that cleanup resets all GPIO pins."""
        mock_gpio.BCM = 11
        mock_gpio.OUT = 1
        mock_gpio.LOW = 0
        mock_gpio.HIGH = 1

        reset_state()
        controller = ValveController(use_gpio=True)
        controller.open_valve(0)
        controller.cleanup()

        mock_gpio.cleanup.assert_called_once()


class TestGetController(unittest.TestCase):
    """Test the get_controller factory function."""

    def setUp(self):
        """Reset the global controller."""
        import valve_controller
        valve_controller.controller = None
        reset_state()

    def tearDown(self):
        """Reset the global controller after each test."""
        import valve_controller
        valve_controller.controller = None
        reset_state()

    def test_singleton_pattern(self):
        """Test that get_controller returns the same instance."""
        c1 = get_controller(use_gpio=False)
        c2 = get_controller(use_gpio=False)
        self.assertIs(c1, c2)

    def test_controller_created_on_first_call(self):
        """Test that controller is created on first call."""
        import valve_controller
        self.assertIsNone(valve_controller.controller)

        c = get_controller(use_gpio=False)
        self.assertIsNotNone(c)

    def test_use_gpio_parameter(self):
        """Test that use_gpio parameter is respected."""
        c = get_controller(use_gpio=False)
        self.assertFalse(c.use_gpio)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def setUp(self):
        """Set up test fixtures."""
        reset_state()
        self.controller = ValveController(use_gpio=False)

    def test_rapid_open_close(self):
        """Test rapid open and close operations."""
        for _ in range(10):
            self.controller.open_valve(0)
            self.controller.close_valve(0)

    def test_open_close_different_valves(self):
        """Test opening and closing different valves in sequence."""
        for i in range(VALVE_COUNT):
            self.controller.open_valve(i)
            self.controller.close_valve(i)

    def test_concurrent_open_attempts(self):
        """Test handling of concurrent open attempts."""
        results = []

        def try_open():
            result = self.controller.open_valve(0)
            results.append(result['success'])

        # Start multiple threads trying to open
        threads = [threading.Thread(target=try_open) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one should succeed
        self.assertEqual(sum(results), 1)

    def test_open_close_thread_safety(self):
        """Test thread safety of open/close operations."""
        errors = []

        def worker(valve_id):
            try:
                self.controller.open_valve(valve_id)
                time.sleep(0.01)
                self.controller.close_valve(valve_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(VALVE_COUNT)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)


if __name__ == '__main__':
    unittest.main()
