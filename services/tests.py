"""Tests for instrument connection lifecycle and locking."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from drivers.exceptions import ConnectionError

from .connection_manager import ConnectionManager


class ConnectionManagerTests(SimpleTestCase):
    """Verify process-local connection ownership and cleanup."""

    def setUp(self):
        """Create a saved instrument-like object for manager tests."""
        self.instrument = SimpleNamespace(
            pk=42,
            driver="keysight_34461a",
            address="/dev/usbtmc0",
        )

    def tearDown(self):
        """Release process-local connections after every test."""
        ConnectionManager.disconnect_all()

    def connected_driver(self):
        """Return a mock driver whose connect/disconnect update its state."""
        driver = MagicMock()
        driver.connected = False
        driver.connect.side_effect = lambda: setattr(driver, "connected", True)
        driver.disconnect.side_effect = lambda: setattr(
            driver,
            "connected",
            False,
        )
        return driver

    @patch("services.connection_manager.create_driver")
    def test_connect_opens_and_caches_driver(self, factory):
        """Repeated connects reuse one active driver."""
        driver = self.connected_driver()
        factory.return_value = driver

        first = ConnectionManager.connect(self.instrument)
        second = ConnectionManager.connect(self.instrument)

        self.assertIs(first, driver)
        self.assertIs(second, driver)
        factory.assert_called_once_with(self.instrument)
        driver.connect.assert_called_once()
        self.assertTrue(ConnectionManager.is_connected(self.instrument))

    @patch("services.connection_manager.create_driver")
    def test_temporary_session_guarantees_disconnect(self, factory):
        """A session that opened a connection closes it after use."""
        driver = self.connected_driver()
        factory.return_value = driver

        with ConnectionManager.session(self.instrument) as active:
            self.assertIs(active, driver)
            self.assertTrue(ConnectionManager.is_connected(self.instrument))

        driver.disconnect.assert_called_once()
        self.assertFalse(ConnectionManager.is_connected(self.instrument))

    @patch("services.connection_manager.create_driver")
    def test_session_preserves_preexisting_connection(self, factory):
        """A session does not close a connection owned by another caller."""
        driver = self.connected_driver()
        factory.return_value = driver
        ConnectionManager.connect(self.instrument)

        with ConnectionManager.session(self.instrument) as active:
            self.assertIs(active, driver)

        driver.disconnect.assert_not_called()
        self.assertTrue(ConnectionManager.is_connected(self.instrument))

    @patch("services.connection_manager.create_driver")
    def test_failed_connection_is_disconnected_and_not_cached(self, factory):
        """A failed driver is cleaned up and never reported online."""
        driver = self.connected_driver()
        driver.connect.side_effect = ConnectionError("Connection failed.")
        factory.return_value = driver

        with self.assertRaises(ConnectionError):
            ConnectionManager.connect(self.instrument)

        driver.disconnect.assert_called_once()
        self.assertFalse(ConnectionManager.is_connected(self.instrument))

    def test_exclusive_requires_active_connection(self):
        """Exclusive access cannot silently open a missing connection."""
        with self.assertRaises(ConnectionError):
            with ConnectionManager.exclusive(self.instrument):
                pass

    @patch("services.connection_manager.create_driver")
    def test_connected_ids_only_contains_active_connections(self, factory):
        """Online identifiers reflect the manager's live connection cache."""
        driver = self.connected_driver()
        factory.return_value = driver
        ConnectionManager.connect(self.instrument)

        self.assertEqual(ConnectionManager.connected_ids(), frozenset({42}))

        ConnectionManager.disconnect(self.instrument)
        self.assertEqual(ConnectionManager.connected_ids(), frozenset())
