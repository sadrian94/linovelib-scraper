import unittest
from unittest.mock import MagicMock, patch

from backend.browser_utils import cleanup_browser_profile, create_browser


class TestBrowserProfiles(unittest.TestCase):
    @patch("backend.browser_utils.Chromium")
    @patch("backend.browser_utils.ChromiumOptions")
    def test_create_browser_uses_an_isolated_profile(self, mock_options, mock_chromium):
        browser = MagicMock()
        mock_chromium.return_value = browser

        result = create_browser()

        profile_path = browser._linovelib_profile_path
        mock_options.return_value.set_user_data_path.assert_called_once_with(profile_path)
        self.assertTrue(profile_path)
        cleanup_browser_profile(result)

    def test_cleanup_ignores_profiles_outside_the_temp_profile_root(self):
        browser = MagicMock()
        browser._linovelib_profile_path = "C:/not-a-linovelib-profile"

        cleanup_browser_profile(browser)


if __name__ == "__main__":
    unittest.main()
