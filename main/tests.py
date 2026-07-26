from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Instrument, UserPreference


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

    def test_dashboard_counts_online_instruments(self):
        """Dashboard reports total and currently online inventory counts."""
        Instrument.objects.create(
            name="Online DMM",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
            status=Instrument.Status.ONLINE,
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
        self.assertEqual(response.context["online_instrument_count"], 1)

    def test_instruments_navigation_opens_separate_list(self):
        """Dashboard navigation points to the standalone instrument page."""
        response = self.client.get(reverse("dashboard"))

        self.assertContains(
            response,
            f'href="{reverse("instrument_list")}">',
        )
        self.assertNotContains(response, "No instruments have been added yet.")
