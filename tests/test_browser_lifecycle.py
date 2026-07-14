import unittest
from unittest.mock import patch, MagicMock
from backend.bilinovel.Editer import Editer

class TestBrowserLifecycle(unittest.TestCase):
    @patch('backend.bilinovel.Editer.create_browser')
    @patch('backend.bilinovel.Editer.Editer.get_html')
    @patch('backend.bilinovel.Editer.Editer.get_meta_data')
    def test_browser_closed_on_success(self, mock_meta, mock_get_html, mock_create_browser):
        mock_browser = MagicMock()
        mock_create_browser.return_value = mock_browser
        
        with Editer(root_path="./out", book_no="1234") as editer:
            self.assertEqual(editer.browser, mock_browser)
        
        # Verify browser quit was called when exiting context manager
        mock_browser.quit.assert_called_once()

    @patch('backend.bilinovel.Editer.create_browser')
    @patch('backend.bilinovel.Editer.Editer.get_html')
    def test_browser_closed_on_init_failure(self, mock_get_html, mock_create_browser):
        mock_browser = MagicMock()
        mock_create_browser.return_value = mock_browser
        # Simulate failure in __init__
        mock_get_html.side_effect = Exception("Init failure")
        
        with self.assertRaises(Exception):
            with Editer(root_path="./out", book_no="1234") as editer:
                pass
                
        # Verify quit was called during init error handling
        mock_browser.quit.assert_called_once()

if __name__ == '__main__':
    unittest.main()
