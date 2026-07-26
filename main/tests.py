from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from drivers.base import FunctionConfiguration
from drivers.exceptions import CommunicationError, ConfigurationError

from .instrument_services import connect_instrument as run_connect
from .instrument_services import disconnect_instrument as run_disconnect
from .instrument_services import (
    test_instrument_dc_voltage_mode as run_dcv_mode_test,
)
from .instrument_services import test_instrument_driver as run_driver_test
from .models import Instrument, Measurement, UserPreference


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
        self.assertEqual(response.context["measurement_count"], 0)

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
