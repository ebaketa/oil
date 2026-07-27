import json
import uuid
from threading import Event
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from drivers.base import FunctionConfiguration, MeasurementResult
from drivers.exceptions import CommunicationError, ConfigurationError

from .instrument_services import connect_instrument as run_connect
from .instrument_services import disconnect_instrument as run_disconnect
from .instrument_services import (
    test_instrument_dc_voltage_mode as run_dcv_mode_test,
)
from .instrument_services import test_instrument_driver as run_driver_test
from .measurement_services import (
    iter_continuous_measurements,
    perform_measurement,
    perform_measurement_loop,
)
from .models import Instrument, Measurement, MeasurementRun, UserPreference


class AuthenticationTests(TestCase):
    """Test login requirements and authentication navigation."""

    @classmethod
    def setUpTestData(cls):
        """Create a user shared by the authentication tests."""
        cls.user = get_user_model().objects.create_user(
            username="oil-user",
            password="test-password",
        )

    def test_anonymous_user_is_redirected_to_login(self):
        """Protected pages redirect anonymous users to the login page."""
        protected_pages = (
            ("dashboard", "/"),
            ("contact", "/contact/"),
            ("about", "/about/"),
            ("profile", "/profile/"),
            ("instrument_list", "/instruments/"),
            ("instrument_create", "/instruments/add/"),
            ("measurement_list", "/measurements/"),
            ("measurement_create", "/measurements/new/"),
            ("measurement_continuous", "/measurements/continuous/"),
            ("measurement_loop", "/measurements/loop/"),
        )

        for route_name, path in protected_pages:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                expected_url = f"{reverse('login')}?next={path}"
                self.assertRedirects(response, expected_url)

    def test_login_page_is_available_to_anonymous_users(self):
        """Anonymous users can open the login form."""
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in")

    def test_valid_login_redirects_to_home(self):
        """Valid credentials authenticate the user and open the dashboard."""
        response = self.client.post(
            reverse("login"),
            {
                "username": "oil-user",
                "password": "test-password",
            },
        )

        self.assertRedirects(response, reverse("dashboard"))

    def test_authenticated_user_can_open_protected_pages(self):
        """Authenticated users can access every protected page."""
        self.client.force_login(self.user)

        for route_name in (
            "dashboard",
            "contact",
            "about",
            "profile",
            "instrument_list",
            "instrument_create",
            "measurement_list",
            "measurement_create",
            "measurement_loop",
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)

    def test_pages_use_consistent_browser_titles(self):
        """Every page title ends with the OIL application name."""
        self.client.force_login(self.user)
        expected_titles = {
            "dashboard": "Dashboard | OIL",
            "contact": "Contact | OIL",
            "about": "About | OIL",
            "profile": "Profile | OIL",
            "instrument_list": "Instruments | OIL",
            "instrument_create": "Add instrument | OIL",
            "measurement_list": "Measurements | OIL",
            "measurement_create": "Single measurement | OIL",
            "measurement_continuous": "Continuous measurement | OIL",
            "measurement_loop": "Measurement loop | OIL",
        }

        for route_name, title in expected_titles.items():
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertContains(response, f"<title>{title}</title>", html=True)

    def test_logout_requires_post_and_redirects_to_login(self):
        """A POST request logs the user out and returns to the login page."""
        self.client.force_login(self.user)

        get_response = self.client.get(reverse("logout"))
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse("logout"))
        self.assertRedirects(post_response, reverse("login"))


class ThemePreferenceTests(TestCase):
    """Test per-user interface theme preferences."""

    @classmethod
    def setUpTestData(cls):
        """Create users shared by the theme preference tests."""
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(
            username="theme-user",
            password="test-password",
        )
        cls.other_user = user_model.objects.create_user(
            username="other-user",
            password="test-password",
        )

    def test_blue_theme_is_used_by_default(self):
        """Users without saved preferences receive the blue theme."""
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "oil-theme-blue")
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())

    def test_user_can_save_theme(self):
        """A valid profile theme is saved and applied to subsequent pages."""
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile"),
            {
                "username": "theme-user",
                "first_name": "",
                "last_name": "",
                "email": "",
                "theme": UserPreference.Theme.ORANGE,
            },
        )

        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(
            UserPreference.objects.get(user=self.user).theme,
            UserPreference.Theme.ORANGE,
        )
        self.assertContains(self.client.get(reverse("about")), "oil-theme-orange")

    def test_theme_preferences_are_separate_for_each_user(self):
        """Changing one user's theme does not affect another user."""
        UserPreference.objects.create(
            user=self.user,
            theme=UserPreference.Theme.RED,
        )
        self.client.force_login(self.other_user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "oil-theme-blue")

    def test_invalid_theme_is_rejected(self):
        """Values outside the configured theme choices are not stored."""
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile"),
            {
                "username": "theme-user",
                "first_name": "",
                "last_name": "",
                "email": "",
                "theme": "invalid-theme",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertEqual(
            UserPreference.objects.get(user=self.user).theme,
            UserPreference.Theme.BLUE,
        )

    def test_user_can_update_account_details(self):
        """Users can update their own account details from the profile."""
        self.client.force_login(self.user)

        self.client.post(
            reverse("profile"),
            {
                "username": "renamed-user",
                "first_name": "Oil",
                "last_name": "Operator",
                "email": "operator@example.com",
                "theme": UserPreference.Theme.GREEN,
            },
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "renamed-user")
        self.assertEqual(self.user.first_name, "Oil")
        self.assertEqual(self.user.last_name, "Operator")
        self.assertEqual(self.user.email, "operator@example.com")

    def test_existing_username_is_rejected_case_insensitively(self):
        """A profile cannot take another user's username."""
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile"),
            {
                "username": "OTHER-USER",
                "first_name": "Oil",
                "last_name": "Operator",
                "email": "operator@example.com",
                "theme": UserPreference.Theme.PURPLE,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This username is already in use.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "theme-user")
        self.assertEqual(
            UserPreference.objects.get(user=self.user).theme,
            UserPreference.Theme.BLUE,
        )

    def test_username_links_to_profile(self):
        """The authenticated username opens the profile page."""
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(
            response,
            f'href="{reverse("profile")}">',
        )


class InstrumentInventoryTests(TestCase):
    """Test instrument creation and Dashboard inventory rendering."""

    @classmethod
    def setUpTestData(cls):
        """Create an authenticated inventory user."""
        cls.user = get_user_model().objects.create_user(
            username="instrument-user",
            password="test-password",
        )

    def setUp(self):
        """Authenticate the inventory user."""
        self.client.force_login(self.user)

    def create_instrument(self, **overrides):
        """Create a Keysight test instrument with optional field overrides."""
        values = {
            "name": "Bench multimeter",
            "manufacturer": "Keysight",
            "model_name": "34461A",
            "serial_number": "MY12345678",
            "driver": Instrument.Driver.KEYSIGHT_34461A,
            "address": "/dev/usbtmc0",
            "description": "Primary bench DMM",
        }
        values.update(overrides)
        return Instrument.objects.create(**values)

    def test_empty_instrument_list_invites_user_to_add_instrument(self):
        """An empty inventory has a clear initial state and add action."""
        response = self.client.get(reverse("instrument_list"))

        self.assertContains(response, "No instruments have been added yet.")
        self.assertContains(response, reverse("instrument_create"))
        self.assertContains(response, reverse("dashboard"))
        self.assertEqual(response.context["instrument_count"], 0)

    def test_user_can_add_instrument(self):
        """A valid instrument is stored offline and shown on Dashboard."""
        response = self.client.post(
            reverse("instrument_create"),
            {
                "name": "Bench multimeter",
                "manufacturer": "Keysight",
                "model_name": "34461A",
                "serial_number": "MY12345678",
                "driver": Instrument.Driver.KEYSIGHT_34461A,
                "address": "/dev/usbtmc0",
                "description": "Primary bench DMM",
            },
        )

        self.assertRedirects(response, reverse("instrument_list"))
        instrument = Instrument.objects.get()
        self.assertEqual(instrument.status, Instrument.Status.OFFLINE)

        instrument_list = self.client.get(reverse("instrument_list"))
        self.assertContains(instrument_list, "Bench multimeter")
        self.assertContains(instrument_list, "Keysight 34461A")
        self.assertContains(instrument_list, "/dev/usbtmc0")
        self.assertEqual(instrument_list.context["instrument_count"], 1)

    def test_user_can_add_mock_instrument(self):
        """The inventory form exposes the hardware-free mock driver."""
        response = self.client.post(
            reverse("instrument_create"),
            {
                "name": "Simulated DMM",
                "manufacturer": "OIL",
                "model_name": "Mock DMM",
                "serial_number": "",
                "driver": Instrument.Driver.MOCK,
                "address": "mock://default",
                "description": "Development instrument",
            },
        )

        self.assertRedirects(response, reverse("instrument_list"))
        instrument = Instrument.objects.get()
        self.assertEqual(instrument.driver, Instrument.Driver.MOCK)
        self.assertEqual(instrument.address, "mock://default")

    def test_invalid_instrument_is_not_created(self):
        """Required fields are validated before an instrument is stored."""
        response = self.client.post(
            reverse("instrument_create"),
            {
                "name": "Incomplete instrument",
                "manufacturer": "",
                "model_name": "",
                "driver": "",
                "address": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertFalse(Instrument.objects.exists())

    def test_dashboard_distinguishes_online_and_reachable(self):
        """Dashboard separates open connections from successful last tests."""
        Instrument.objects.create(
            name="Reachable DMM",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
            status=Instrument.Status.REACHABLE,
        )
        Instrument.objects.create(
            name="Offline DMM",
            manufacturer="Keysight",
            model_name="34461A",
            driver=Instrument.Driver.KEYSIGHT_34461A,
            address="/dev/usbtmc0",
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.context["instrument_count"], 2)
        self.assertEqual(response.context["online_instrument_count"], 0)
        self.assertEqual(response.context["reachable_instrument_count"], 1)

    def test_dashboard_status_card_is_last(self):
        """Status remains after the other Dashboard summary cards."""
        response = self.client.get(reverse("dashboard"))
        content = response.content.decode()

        self.assertLess(
            content.index(">Measurements</div>"),
            content.index(">Status</div>"),
        )

    @patch("main.views.ConnectionManager.connected_ids")
    def test_dashboard_online_count_uses_active_manager_connections(
        self,
        connected_ids,
    ):
        """Online count comes from live connections rather than DB status."""
        instrument = self.create_instrument()
        connected_ids.return_value = frozenset({instrument.pk})

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.context["online_instrument_count"], 1)

    @patch("main.views.ConnectionManager.connected_ids")
    def test_online_instrument_is_not_also_counted_as_reachable(
        self,
        connected_ids,
    ):
        """Dashboard status groups are mutually exclusive."""
        online = self.create_instrument(
            name="Online DMM",
            status=Instrument.Status.REACHABLE,
        )
        self.create_instrument(
            name="Reachable DMM",
            address="/dev/usbtmc1",
            status=Instrument.Status.REACHABLE,
        )
        connected_ids.return_value = frozenset({online.pk})

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.context["online_instrument_count"], 1)
        self.assertEqual(response.context["reachable_instrument_count"], 1)

    def test_instrument_name_links_to_edit_page(self):
        """Selecting an instrument name opens its settings form."""
        instrument = self.create_instrument()

        response = self.client.get(reverse("instrument_list"))

        self.assertContains(
            response,
            reverse("instrument_edit", args=[instrument.pk]),
        )

    def test_driver_name_links_to_driver_page(self):
        """Selecting a driver opens its details and test page."""
        instrument = self.create_instrument()

        response = self.client.get(reverse("instrument_list"))

        self.assertContains(
            response,
            reverse("instrument_driver", args=[instrument.pk]),
        )

    @patch("main.views.ConnectionManager.connected_ids")
    def test_instrument_list_offers_connect_when_disconnected(
        self,
        connected_ids,
    ):
        """A disconnected instrument displays a protected Connect action."""
        instrument = self.create_instrument()
        connected_ids.return_value = frozenset()

        response = self.client.get(reverse("instrument_list"))

        self.assertContains(response, "Reachable")
        self.assertNotContains(response, "Offline")
        self.assertNotContains(response, "Disconnected")
        self.assertContains(
            response,
            reverse("instrument_connect", args=[instrument.pk]),
        )
        self.assertNotContains(
            response,
            reverse("instrument_disconnect", args=[instrument.pk]),
        )

    @patch("main.views.ConnectionManager.connected_ids")
    def test_instrument_list_offers_disconnect_when_online(
        self,
        connected_ids,
    ):
        """An active instrument displays its Disconnect action."""
        instrument = self.create_instrument()
        connected_ids.return_value = frozenset({instrument.pk})

        response = self.client.get(reverse("instrument_list"))

        self.assertContains(response, "Online")
        self.assertContains(
            response,
            reverse("instrument_disconnect", args=[instrument.pk]),
        )

    @patch("main.views.connect_instrument")
    def test_connect_action_uses_service_and_redirects(self, connect):
        """Connect POST delegates to the service and returns to the list."""
        instrument = self.create_instrument()

        response = self.client.post(
            reverse("instrument_connect", args=[instrument.pk]),
            follow=True,
        )

        self.assertRedirects(
            response,
            reverse("instrument_list"),
            status_code=302,
            target_status_code=200,
        )
        self.assertContains(response, f"{instrument.name} is connected.")
        self.assertContains(response, 'data-auto-dismiss="4000"')
        self.assertContains(response, 'data-bs-dismiss="alert"')
        connect.assert_called_once()
        self.assertEqual(connect.call_args.args[0], instrument)

    @patch("main.views.disconnect_instrument")
    def test_disconnect_action_uses_service_and_redirects(self, disconnect):
        """Disconnect POST delegates to the service and returns to the list."""
        instrument = self.create_instrument()

        response = self.client.post(
            reverse("instrument_disconnect", args=[instrument.pk]),
        )

        self.assertRedirects(response, reverse("instrument_list"))
        disconnect.assert_called_once()
        self.assertEqual(disconnect.call_args.args[0], instrument)

    def test_connection_actions_reject_get_requests(self):
        """A link or crawler cannot change hardware connection state."""
        instrument = self.create_instrument()

        for route_name in ("instrument_connect", "instrument_disconnect"):
            with self.subTest(route_name=route_name):
                response = self.client.get(
                    reverse(route_name, args=[instrument.pk]),
                )
                self.assertEqual(response.status_code, 405)

    def test_edit_form_is_populated_with_instrument_settings(self):
        """The edit page displays the selected instrument's current values."""
        instrument = self.create_instrument()

        response = self.client.get(
            reverse("instrument_edit", args=[instrument.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Edit instrument | OIL</title>", html=True)
        self.assertEqual(response.context["form"].instance, instrument)
        self.assertContains(response, instrument.address)

    def test_user_can_edit_instrument_settings(self):
        """Valid edits are saved while driver-controlled status is preserved."""
        instrument = self.create_instrument(status=Instrument.Status.REACHABLE)

        response = self.client.post(
            reverse("instrument_edit", args=[instrument.pk]),
            {
                "name": "Reference multimeter",
                "manufacturer": "Agilent",
                "model_name": "34401A",
                "serial_number": "A9Z22QXP",
                "driver": Instrument.Driver.AGILENT_34401A,
                "address": "/dev/ttyUSB1",
                "description": "Reference DMM",
            },
        )

        self.assertRedirects(response, reverse("instrument_list"))
        instrument.refresh_from_db()
        self.assertEqual(instrument.name, "Reference multimeter")
        self.assertEqual(instrument.driver, Instrument.Driver.AGILENT_34401A)
        self.assertEqual(instrument.address, "/dev/ttyUSB1")
        self.assertEqual(instrument.status, Instrument.Status.REACHABLE)

    def test_unknown_instrument_edit_returns_not_found(self):
        """Editing an instrument that does not exist returns HTTP 404."""
        response = self.client.get(reverse("instrument_edit", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_instrument_edit_requires_login(self):
        """Anonymous users cannot open instrument settings."""
        instrument = self.create_instrument()
        self.client.logout()
        edit_url = reverse("instrument_edit", args=[instrument.pk])

        response = self.client.get(edit_url)

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={edit_url}",
        )

    def test_driver_page_displays_configuration(self):
        """The driver page displays address, status, and test action."""
        instrument = self.create_instrument()

        response = self.client.get(
            reverse("instrument_driver", args=[instrument.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, instrument.get_driver_display())
        self.assertContains(response, instrument.address)
        self.assertContains(
            response,
            reverse("instrument_driver_test", args=[instrument.pk]),
        )
        self.assertContains(
            response,
            reverse("instrument_driver_test_dcv", args=[instrument.pk]),
        )
        self.assertContains(response, "Supported measurement functions")
        self.assertContains(response, "DC voltage")
        self.assertContains(response, "Autorange")
        self.assertContains(response, "<td>V</td>", html=True)

    @patch("main.views.test_instrument_driver", return_value="KEYSIGHT,34461A")
    def test_driver_test_uses_service_and_redirects(self, test_driver):
        """A POST runs the driver service and returns to its details page."""
        instrument = self.create_instrument()
        test_url = reverse("instrument_driver_test", args=[instrument.pk])

        response = self.client.post(test_url)

        self.assertRedirects(
            response,
            reverse("instrument_driver", args=[instrument.pk]),
        )
        test_driver.assert_called_once()
        self.assertEqual(test_driver.call_args.args[0], instrument)

    def test_driver_test_rejects_get_requests(self):
        """Hardware tests cannot be triggered by a GET request."""
        instrument = self.create_instrument()

        response = self.client.get(
            reverse("instrument_driver_test", args=[instrument.pk]),
        )

        self.assertEqual(response.status_code, 405)

    @patch(
        "main.views.test_instrument_dc_voltage_mode",
        return_value=FunctionConfiguration(
            function="Voltage DC",
            autorange=True,
        ),
    )
    def test_dcv_mode_test_uses_service_and_redirects(self, test_dcv):
        """A POST runs DCV verification and returns to driver details."""
        instrument = self.create_instrument()
        test_url = reverse("instrument_driver_test_dcv", args=[instrument.pk])

        response = self.client.post(test_url)

        self.assertRedirects(
            response,
            reverse("instrument_driver", args=[instrument.pk]),
        )
        test_dcv.assert_called_once()
        self.assertEqual(test_dcv.call_args.args[0], instrument)

    def test_instruments_navigation_opens_separate_list(self):
        """Dashboard navigation points to the standalone instrument page."""
        response = self.client.get(reverse("dashboard"))

        self.assertContains(
            response,
            f'href="{reverse("instrument_list")}">',
        )
        self.assertNotContains(response, "No instruments have been added yet.")


class InstrumentDriverServiceTests(TestCase):
    """Test persisted driver results without accessing physical hardware."""

    def create_instrument(self):
        """Create a configured Keysight instrument."""
        return Instrument.objects.create(
            name="Bench multimeter",
            manufacturer="Keysight",
            model_name="34461A",
            driver=Instrument.Driver.KEYSIGHT_34461A,
            address="/dev/usbtmc0",
        )

    @patch("main.instrument_services.ConnectionManager.session")
    def test_successful_test_stores_identity_and_reachable_status(self, session):
        """A successful identification is persisted for later display."""
        instrument = self.create_instrument()
        driver = MagicMock()
        driver.identify.return_value = "KEYSIGHT,34461A,MY123,1.0"
        session.return_value.__enter__.return_value = driver

        identity = run_driver_test(instrument)

        instrument.refresh_from_db()
        self.assertEqual(identity, "KEYSIGHT,34461A,MY123,1.0")
        self.assertEqual(instrument.last_identification, identity)
        self.assertEqual(instrument.status, Instrument.Status.REACHABLE)
        self.assertIsNotNone(instrument.last_driver_test_at)
        self.assertEqual(instrument.last_driver_error, "")
        session.assert_called_once_with(instrument)

    @patch("main.instrument_services.ConnectionManager.session")
    def test_failed_test_stores_error_status(self, session):
        """A driver failure is recorded and remains a domain error."""
        instrument = self.create_instrument()
        session.return_value.__enter__.side_effect = CommunicationError(
            "Device timed out."
        )

        with self.assertRaises(CommunicationError):
            run_driver_test(instrument)

        instrument.refresh_from_db()
        self.assertEqual(instrument.status, Instrument.Status.ERROR)
        self.assertEqual(instrument.last_driver_error, "Device timed out.")
        self.assertIsNotNone(instrument.last_driver_test_at)

    @patch("main.instrument_services.ConnectionManager.session")
    def test_dcv_mode_success_stores_reachable_status(self, session):
        """Verified DCV mode is recorded as a successful driver test."""
        instrument = self.create_instrument()
        driver = MagicMock()
        driver.configure_dc_voltage_auto.return_value = FunctionConfiguration(
            function="Voltage DC",
            autorange=True,
        )
        session.return_value.__enter__.return_value = driver

        result = run_dcv_mode_test(instrument)

        instrument.refresh_from_db()
        self.assertTrue(result.autorange)
        self.assertEqual(instrument.status, Instrument.Status.REACHABLE)
        self.assertEqual(instrument.last_driver_error, "")
        self.assertIsNotNone(instrument.last_driver_test_at)

    @patch("main.instrument_services.ConnectionManager.session")
    def test_dcv_mode_mismatch_stores_error(self, session):
        """A read-back mismatch is persisted as a driver error."""
        instrument = self.create_instrument()
        driver = MagicMock()
        driver.configure_dc_voltage_auto.side_effect = ConfigurationError(
            "DC voltage autorange was not enabled by the instrument."
        )
        session.return_value.__enter__.return_value = driver

        with self.assertRaises(ConfigurationError):
            run_dcv_mode_test(instrument)

        instrument.refresh_from_db()
        self.assertEqual(instrument.status, Instrument.Status.ERROR)
        self.assertIn("autorange", instrument.last_driver_error)

    @patch("main.instrument_services.ConnectionManager.connect")
    def test_connect_stores_reachable_status(self, connect):
        """A retained connection records a successful operation."""
        instrument = self.create_instrument()

        run_connect(instrument)

        instrument.refresh_from_db()
        connect.assert_called_once_with(instrument)
        self.assertEqual(instrument.status, Instrument.Status.REACHABLE)
        self.assertEqual(instrument.last_driver_error, "")

    @patch("main.instrument_services.ConnectionManager.connect")
    def test_connect_failure_stores_driver_error(self, connect):
        """A failed connection is visible in the persisted status."""
        instrument = self.create_instrument()
        connect.side_effect = CommunicationError("Device is unavailable.")

        with self.assertRaises(CommunicationError):
            run_connect(instrument)

        instrument.refresh_from_db()
        self.assertEqual(instrument.status, Instrument.Status.ERROR)
        self.assertEqual(
            instrument.last_driver_error,
            "Device is unavailable.",
        )

    @patch("main.instrument_services.ConnectionManager.disconnect")
    def test_disconnect_closes_managed_connection(self, disconnect):
        """Disconnect delegates lifecycle cleanup to the manager."""
        instrument = self.create_instrument()

        run_disconnect(instrument)

        disconnect.assert_called_once_with(instrument)


class MeasurementRunModelTests(TestCase):
    """Test persistent measurement series metadata and relationships."""

    def setUp(self):
        """Create a user and instrument used by run model tests."""
        self.user = get_user_model().objects.create_user(
            username="run-user",
            password="test-password",
        )
        self.instrument = Instrument.objects.create(
            name="Run DMM",
            manufacturer="Keysight",
            model_name="34461A",
            driver=Instrument.Driver.KEYSIGHT_34461A,
            address="/dev/usbtmc0",
        )

    def create_run(self, **overrides):
        """Create a representative loop run."""
        values = {
            "user": self.user,
            "instrument": self.instrument,
            "function": MeasurementRun.Function.DC_VOLTAGE,
            "mode": MeasurementRun.Mode.LOOP,
            "interval": 0.5,
            "requested_count": 10,
            "notes": "Stability run",
        }
        values.update(overrides)
        return MeasurementRun.objects.create(**values)

    def test_run_stores_configuration_and_pending_lifecycle(self):
        """A new run records its owner, settings, and pending state."""
        run = self.create_run()

        self.assertEqual(run.user, self.user)
        self.assertEqual(run.instrument, self.instrument)
        self.assertEqual(run.function, MeasurementRun.Function.DC_VOLTAGE)
        self.assertEqual(run.mode, MeasurementRun.Mode.LOOP)
        self.assertEqual(run.interval, 0.5)
        self.assertEqual(run.requested_count, 10)
        self.assertEqual(run.status, MeasurementRun.Status.PENDING)
        self.assertIsNone(run.started_at)
        self.assertIsNone(run.stopped_at)
        self.assertEqual(str(run), "Loop DC voltage on Run DMM")

    def test_measurements_can_belong_to_a_run(self):
        """Readings expose their run through both relationship directions."""
        run = self.create_run()
        measurement = Measurement.objects.create(
            run=run,
            instrument=self.instrument,
            parameter="Voltage DC",
            value=1.234,
            unit="V",
        )

        self.assertEqual(measurement.run, run)
        self.assertEqual(list(run.measurements.all()), [measurement])

    def test_measurement_protects_its_run_from_deletion(self):
        """A run with stored readings cannot be deleted accidentally."""
        run = self.create_run()
        Measurement.objects.create(
            run=run,
            instrument=self.instrument,
            parameter="Voltage DC",
            value=1.234,
            unit="V",
        )

        with self.assertRaises(ProtectedError):
            run.delete()

    def test_deleted_user_does_not_delete_run_history(self):
        """Deleting an account preserves its historical measurement runs."""
        run = self.create_run()

        self.user.delete()
        run.refresh_from_db()

        self.assertIsNone(run.user)

    def test_interval_below_supported_minimum_is_rejected(self):
        """Run validation rejects intervals shorter than 0.1 seconds."""
        run = self.create_run(interval=0.05)

        with self.assertRaises(ValidationError):
            run.full_clean()


class MeasurementListTests(TestCase):
    """Test measurement storage, listing, and Dashboard summary."""

    @classmethod
    def setUpTestData(cls):
        """Create an authenticated user and configured instrument."""
        cls.user = get_user_model().objects.create_user(
            username="measurement-user",
            password="test-password",
        )
        cls.instrument = Instrument.objects.create(
            name="Reference DMM",
            manufacturer="Keysight",
            model_name="34461A",
            driver=Instrument.Driver.KEYSIGHT_34461A,
            address="/dev/usbtmc0",
        )

    def setUp(self):
        """Authenticate the measurement user."""
        self.client.force_login(self.user)

    def test_empty_measurement_page_has_initial_state(self):
        """The measurement list explains when no readings exist."""
        response = self.client.get(reverse("measurement_list"))

        self.assertContains(response, "No measurements have been recorded yet.")
        self.assertContains(response, reverse("measurement_create"))
        self.assertEqual(response.context["measurement_count"], 0)

    def test_new_measurement_page_offers_supported_choices(self):
        """The form offers every function supported by the selected driver."""
        response = self.client.get(reverse("measurement_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Single measurement | OIL</title>",
            html=True,
        )
        self.assertContains(response, "Reference DMM")
        self.assertContains(response, "DC voltage")
        self.assertContains(response, "AC voltage")
        self.assertContains(response, "Resistance")
        self.assertContains(response, "Measure")
        self.assertContains(response, "Measurement result")
        self.assertContains(
            response,
            "No single measurement has been recorded yet.",
        )

    def test_measurement_list_links_to_loop_form(self):
        """The measurement list offers a separate Loop action."""
        response = self.client.get(reverse("measurement_list"))

        self.assertContains(response, reverse("measurement_loop"))
        self.assertContains(response, "Loop")

    def test_measurement_list_links_to_continuous_form(self):
        """Continuous appears between the Single and Loop actions."""
        response = self.client.get(reverse("measurement_list"))
        content = response.content.decode()

        self.assertContains(response, reverse("measurement_continuous"))
        self.assertLess(content.index("Single"), content.index("Continuous"))
        self.assertLess(content.index("Continuous"), content.index("Loop"))

    def test_continuous_form_offers_start_and_stop_controls(self):
        """The continuous page exposes settings and live result controls."""
        response = self.client.get(reverse("measurement_continuous"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Continuous measurement | OIL</title>",
            html=True,
        )
        self.assertContains(response, "Measurement (Function)")
        self.assertContains(response, "Interval (seconds)")
        self.assertContains(response, "Start")
        self.assertContains(response, "Stop")
        self.assertContains(response, "Measurement results")

    @patch("main.views.iter_continuous_measurements")
    def test_continuous_stream_returns_live_ndjson(self, iterate):
        """The continuous endpoint streams every yielded stored reading."""
        first = Measurement.objects.create(
            instrument=self.instrument,
            parameter="Voltage DC",
            value=2.0,
            unit="V",
        )
        second = Measurement.objects.create(
            instrument=self.instrument,
            parameter="Voltage DC",
            value=2.1,
            unit="V",
        )
        iterate.return_value = iter((first, second))
        session_id = str(uuid.uuid4())

        response = self.client.post(
            reverse("measurement_continuous_stream"),
            {
                "instrument": self.instrument.pk,
                "measurement_type": "dc_voltage",
                "interval_seconds": 0.5,
                "notes": "Monitor",
                "session_id": session_id,
            },
        )
        records = [
            json.loads(line)
            for line in b"".join(response.streaming_content).decode().splitlines()
        ]

        self.assertEqual(response.status_code, 200)
        self.assertEqual([record["index"] for record in records], [1, 2])
        self.assertEqual([record["value"] for record in records], [2.0, 2.1])
        iterate.assert_called_once()

    @patch(
        "drivers.registry.DriverRegistry.capabilities",
        return_value={},
    )
    @patch("main.views.perform_measurement")
    def test_unsupported_driver_function_is_rejected(
        self,
        perform,
        _capabilities,
    ):
        """The backend rejects a function absent from driver capabilities."""
        response = self.client.post(
            reverse("measurement_single_result"),
            {
                "instrument": self.instrument.pk,
                "measurement_type": "dc_voltage",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "does not support this measurement",
            response.json()["errors"]["measurement_type"][0]["message"],
        )
        perform.assert_not_called()

    def test_continuous_stop_signals_owned_session(self):
        """Stop accepts an active session belonging to the signed-in user."""
        from .continuous_sessions import ContinuousSessionRegistry

        session_id = str(uuid.uuid4())
        stop_event = ContinuousSessionRegistry.start(session_id, self.user.pk)
        try:
            response = self.client.post(
                reverse("measurement_continuous_stop"),
                {"session_id": session_id},
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(stop_event.is_set())
        finally:
            ContinuousSessionRegistry.finish(session_id)

    def test_loop_form_accepts_bounded_series_settings(self):
        """The loop page shows instrument, count, and interval controls."""
        response = self.client.get(reverse("measurement_loop"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Measurement loop | OIL</title>",
            html=True,
        )
        self.assertContains(response, "Measurement (Function)")
        self.assertContains(response, "Number of measurements")
        self.assertContains(response, "Interval (seconds)")
        self.assertContains(response, "Notes")
        self.assertContains(response, "Start")
        self.assertContains(response, "Measurement results")
        self.assertContains(
            response,
            "No loop measurements have been recorded yet.",
        )

    @patch("main.views.perform_measurement")
    def test_valid_form_performs_measurement_and_displays_result(self, perform):
        """A valid request displays the measured value below the form."""
        perform.return_value = Measurement(
            instrument=self.instrument,
            parameter="Voltage DC",
            value=1.25,
            unit="V",
        )

        response = self.client.post(
            reverse("measurement_create"),
            {
                "instrument": self.instrument.pk,
                "measurement_type": "dc_voltage",
                "notes": "Input reference",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Measurement result")
        self.assertContains(response, "Reference DMM")
        self.assertContains(response, "Voltage DC")
        self.assertContains(response, "1.25")
        self.assertContains(response, "DC voltage")
        self.assertContains(response, "Input reference")
        self.assertContains(response, 'id="measurement-single-repeat"', html=False)
        self.assertEqual(
            response.context["measurement_summary"]["instrument"],
            "Reference DMM (Keysight 34461A)",
        )
        perform.assert_called_once_with(
            self.instrument,
            "dc_voltage",
            notes="Input reference",
        )

    @patch("main.views.perform_measurement")
    def test_single_result_endpoint_returns_live_table_row(self, perform):
        """Each Single request returns one result that JavaScript can append."""
        perform.return_value = Measurement(
            instrument=self.instrument,
            parameter="Voltage DC",
            value=1.5,
            unit="V",
            timestamp=timezone.now(),
        )

        response = self.client.post(
            reverse("measurement_single_result"),
            {
                "instrument": self.instrument.pk,
                "measurement_type": "dc_voltage",
                "notes": "Repeated reading",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["instrument"], "Reference DMM")
        self.assertEqual(response.json()["parameter"], "Voltage DC")
        self.assertEqual(response.json()["value"], 1.5)
        perform.assert_called_once_with(
            self.instrument,
            "dc_voltage",
            notes="Repeated reading",
        )

    @patch("main.views.perform_measurement")
    def test_driver_error_is_displayed_without_redirect(self, perform):
        """Hardware errors remain on the measurement form."""
        perform.side_effect = CommunicationError("Device timed out.")

        response = self.client.post(
            reverse("measurement_create"),
            {
                "instrument": self.instrument.pk,
                "measurement_type": "dc_voltage",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Measurement failed: Device timed out.",
        )

    @patch("main.views.perform_measurement_loop")
    def test_valid_loop_form_runs_series_and_displays_results(self, perform_loop):
        """Valid loop settings display the completed series below the form."""
        perform_loop.return_value = [
            Measurement(
                instrument=self.instrument,
                parameter="Voltage DC",
                value=value,
                unit="V",
            )
            for value in (1.0, 1.1, 1.2)
        ]

        response = self.client.post(
            reverse("measurement_loop"),
            {
                "instrument": self.instrument.pk,
                "measurement_type": "dc_voltage",
                "count": 3,
                "interval_seconds": 0.5,
                "notes": "Stability run",
            },
        )

        self.assertEqual(response.status_code, 200)
        perform_loop.assert_called_once_with(
            self.instrument,
            "dc_voltage",
            count=3,
            interval_seconds=0.5,
            notes="Stability run",
        )
        self.assertEqual(len(response.context["measurements"]), 3)
        self.assertEqual(
            response.context["loop_summary"]["instrument"],
            str(self.instrument),
        )
        self.assertEqual(
            response.context["loop_summary"]["measurement"],
            "DC voltage",
        )
        self.assertEqual(response.context["loop_summary"]["count"], 3)
        self.assertEqual(
            response.context["loop_summary"]["interval_seconds"],
            0.5,
        )
        self.assertContains(response, "Stability run")
        self.assertContains(response, 'class="mb-4 d-none"')
        self.assertContains(response, "1.0")
        self.assertContains(response, "1.1")
        self.assertContains(response, "1.2")
        self.assertNotContains(
            response,
            "No loop measurements have been recorded yet.",
        )

    @patch("main.views.perform_measurement_loop")
    def test_loop_form_displays_hardware_error(self, perform_loop):
        """A failed series remains on its form with a useful error."""
        perform_loop.side_effect = CommunicationError("Device timed out.")

        response = self.client.post(
            reverse("measurement_loop"),
            {
                "instrument": self.instrument.pk,
                "measurement_type": "dc_voltage",
                "count": 3,
                "interval_seconds": 0.5,
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Measurement loop failed: Device timed out.",
        )

    def test_loop_form_rejects_unsafe_limits(self):
        """Count and interval constraints are validated before hardware use."""
        response = self.client.post(
            reverse("measurement_loop"),
            {
                "instrument": self.instrument.pk,
                "measurement_type": "dc_voltage",
                "count": 101,
                "interval_seconds": 0,
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Ensure this value is less than or equal to 100.",
        )
        self.assertContains(
            response,
            "Ensure this value is greater than or equal to 0.1.",
        )

    @patch("main.views.iter_measurement_loop")
    def test_loop_stream_returns_each_result_as_ndjson(self, iterate):
        """The live endpoint streams one JSON record per measurement."""
        first = Measurement.objects.create(
            instrument=self.instrument,
            parameter="Voltage DC",
            value=1.0,
            unit="V",
        )
        second = Measurement.objects.create(
            instrument=self.instrument,
            parameter="Voltage DC",
            value=1.1,
            unit="V",
        )
        iterate.return_value = iter((first, second))

        response = self.client.post(
            reverse("measurement_loop_stream"),
            {
                "instrument": self.instrument.pk,
                "measurement_type": "dc_voltage",
                "count": 2,
                "interval_seconds": 0.5,
                "notes": "Live run",
            },
        )
        payload = b"".join(response.streaming_content).decode()
        records = [json.loads(line) for line in payload.splitlines()]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/x-ndjson")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        self.assertEqual([record["index"] for record in records], [1, 2])
        self.assertEqual([record["value"] for record in records], [1.0, 1.1])
        iterate.assert_called_once_with(
            self.instrument,
            "dc_voltage",
            count=2,
            interval_seconds=0.5,
            notes="Live run",
        )

    def test_loop_stream_rejects_invalid_settings_before_streaming(self):
        """Invalid live requests return structured validation errors."""
        response = self.client.post(
            reverse("measurement_loop_stream"),
            {
                "instrument": self.instrument.pk,
                "measurement_type": "dc_voltage",
                "count": 101,
                "interval_seconds": 0,
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("count", response.json()["errors"])
        self.assertIn("interval_seconds", response.json()["errors"])

    def test_measurement_page_displays_stored_reading(self):
        """A stored reading is shown with instrument, parameter, and unit."""
        Measurement.objects.create(
            instrument=self.instrument,
            parameter="Voltage DC",
            value=1.2345,
            unit="V",
        )

        response = self.client.get(reverse("measurement_list"))

        self.assertContains(response, "Reference DMM")
        self.assertContains(response, "Voltage DC")
        self.assertContains(response, "1.2345")
        self.assertContains(response, "<td>V</td>", html=True)
        self.assertEqual(response.context["measurement_count"], 1)

    def test_dashboard_measurement_card_links_and_counts(self):
        """Dashboard measurement card links to the list and shows its count."""
        Measurement.objects.create(
            instrument=self.instrument,
            parameter="Voltage DC",
            value=5.0,
            unit="V",
        )

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, reverse("measurement_list"))
        self.assertContains(response, "Measurements")
        self.assertEqual(response.context["measurement_count"], 1)


class MeasurementServiceTests(TestCase):
    """Test measurement execution without accessing physical hardware."""

    def setUp(self):
        """Create an instrument used by measurement service tests."""
        self.instrument = Instrument.objects.create(
            name="Reference DMM",
            manufacturer="Keysight",
            model_name="34461A",
            driver=Instrument.Driver.KEYSIGHT_34461A,
            address="/dev/usbtmc0",
        )

    @patch("main.measurement_services.ConnectionManager.temporary_session")
    def test_dc_voltage_measurement_is_stored(self, session):
        """A normalized driver result is persisted with user notes."""
        driver = MagicMock()
        driver.measure_dc_voltage.return_value = MeasurementResult(
            parameter="Voltage DC",
            value=1.234,
            unit="V",
        )
        session.return_value.__enter__.return_value = driver

        measurement = perform_measurement(
            self.instrument,
            "dc_voltage",
            notes="Reference input",
        )

        self.instrument.refresh_from_db()
        self.assertEqual(Measurement.objects.count(), 1)
        self.assertEqual(measurement.value, 1.234)
        self.assertEqual(measurement.unit, "V")
        self.assertEqual(measurement.notes, "Reference input")
        self.assertEqual(self.instrument.status, Instrument.Status.REACHABLE)
        self.assertEqual(self.instrument.last_driver_error, "")

    @patch("main.measurement_services.ConnectionManager.temporary_session")
    def test_ac_voltage_measurement_dispatches_to_driver(self, session):
        """AC voltage calls its driver method and stores volts."""
        driver = MagicMock()
        driver.measure_ac_voltage.return_value = MeasurementResult(
            parameter="Voltage AC",
            value=2.75,
            unit="V",
        )
        session.return_value.__enter__.return_value = driver

        measurement = perform_measurement(self.instrument, "ac_voltage")

        driver.measure_ac_voltage.assert_called_once_with()
        driver.measure_dc_voltage.assert_not_called()
        driver.measure_resistance.assert_not_called()
        self.assertEqual(measurement.parameter, "Voltage AC")
        self.assertEqual(measurement.value, 2.75)
        self.assertEqual(measurement.unit, "V")

    @patch("main.measurement_services.ConnectionManager.temporary_session")
    def test_resistance_measurement_dispatches_to_driver(self, session):
        """Resistance calls its driver method and stores ohms."""
        driver = MagicMock()
        driver.measure_resistance.return_value = MeasurementResult(
            parameter="Resistance",
            value=1000,
            unit="Ω",
        )
        session.return_value.__enter__.return_value = driver

        measurement = perform_measurement(self.instrument, "resistance")

        driver.measure_resistance.assert_called_once_with()
        driver.measure_dc_voltage.assert_not_called()
        driver.measure_ac_voltage.assert_not_called()
        self.assertEqual(measurement.parameter, "Resistance")
        self.assertEqual(measurement.value, 1000)
        self.assertEqual(measurement.unit, "Ω")

    def test_mock_driver_runs_complete_measurement_service_without_hardware(self):
        """The real service path stores a deterministic simulated reading."""
        mock_instrument = Instrument.objects.create(
            name="Simulated DMM",
            manufacturer="OIL",
            model_name="Mock DMM",
            driver=Instrument.Driver.MOCK,
            address="mock://default",
        )

        measurement = perform_measurement(
            mock_instrument,
            "dc_voltage",
            notes="Hardware-free test",
        )

        mock_instrument.refresh_from_db()
        self.assertEqual(measurement.value, 1.0)
        self.assertEqual(measurement.unit, "V")
        self.assertEqual(measurement.notes, "Hardware-free test")
        self.assertEqual(mock_instrument.status, Instrument.Status.REACHABLE)

    @patch("main.measurement_services.ConnectionManager.temporary_session")
    def test_measurement_failure_does_not_store_a_result(self, session):
        """A hardware failure records an error without creating a reading."""
        session.return_value.__enter__.side_effect = CommunicationError(
            "Device timed out."
        )

        with self.assertRaises(CommunicationError):
            perform_measurement(self.instrument, "dc_voltage")

        self.instrument.refresh_from_db()
        self.assertFalse(Measurement.objects.exists())
        self.assertEqual(self.instrument.status, Instrument.Status.ERROR)
        self.assertEqual(
            self.instrument.last_driver_error,
            "Device timed out.",
        )

    @patch("main.measurement_services.time.sleep")
    @patch("main.measurement_services.ConnectionManager.temporary_session")
    def test_loop_uses_one_session_and_requested_intervals(
        self,
        session,
        sleep,
    ):
        """A series reuses its connection and waits only between readings."""
        driver = MagicMock()
        driver.measure_dc_voltage.side_effect = (
            MeasurementResult("Voltage DC", 1.0, "V"),
            MeasurementResult("Voltage DC", 1.1, "V"),
            MeasurementResult("Voltage DC", 1.2, "V"),
        )
        session.return_value.__enter__.return_value = driver

        measurements = perform_measurement_loop(
            self.instrument,
            "dc_voltage",
            count=3,
            interval_seconds=0.5,
            notes="Stability run",
        )

        session.assert_called_once_with(self.instrument)
        self.assertEqual(driver.measure_dc_voltage.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(0.5)
        self.assertEqual(len(measurements), 3)
        self.assertEqual(Measurement.objects.count(), 3)

    @patch("main.measurement_services.ConnectionManager.temporary_session")
    def test_continuous_measurement_reuses_connection_until_stopped(
        self,
        session,
    ):
        """Continuous readings share one session and stop via an Event."""
        driver = MagicMock()
        driver.measure_dc_voltage.side_effect = (
            MeasurementResult("Voltage DC", 1.0, "V"),
            MeasurementResult("Voltage DC", 1.1, "V"),
        )
        session.return_value.__enter__.return_value = driver
        stop_event = MagicMock(spec=Event)
        stop_event.is_set.return_value = False
        stop_event.wait.side_effect = (False, True)

        measurements = list(
            iter_continuous_measurements(
                self.instrument,
                "dc_voltage",
                interval_seconds=0.5,
                stop_event=stop_event,
                notes="Monitor",
            ),
        )

        session.assert_called_once_with(self.instrument)
        self.assertEqual(driver.measure_dc_voltage.call_count, 2)
        self.assertEqual(stop_event.wait.call_count, 2)
        self.assertEqual(len(measurements), 2)
        self.assertEqual(Measurement.objects.count(), 2)
