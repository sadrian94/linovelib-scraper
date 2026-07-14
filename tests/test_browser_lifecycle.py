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

    @patch('backend.bilinovel.bilinovel_router.Editer')
    def test_query_chaps_context_manager(self, mock_editer_class):
        mock_editer_instance = MagicMock()
        mock_editer_class.return_value = mock_editer_instance
        
        from backend.bilinovel.bilinovel_router import query_chaps
        query_chaps("1234")
        
        # Verify it was used as a context manager
        mock_editer_class.assert_called_once_with(root_path="./out", book_no="1234")
        mock_editer_instance.__enter__.assert_called_once()
        mock_editer_instance.__exit__.assert_called_once()

    @patch('backend.bilinovel.bilinovel_router.Editer')
    def test_download_single_volume_context_manager(self, mock_editer_class):
        mock_editer_instance = MagicMock()
        # Ensure success = editer.get_index_url() returns True so it completes
        mock_editer_instance.get_index_url.return_value = True
        mock_editer_class.return_value = mock_editer_instance
        
        # Set up some attributes that are accessed
        mock_editer_instance.book_name = "Test Book"
        mock_editer_instance.author = "Test Author"
        mock_editer_instance.volume = {"volume_name": "Vol 1"}
        
        from backend.bilinovel.bilinovel_router import download_single_volume
        download_single_volume(
            root_path="./out",
            book_no="1234",
            volume_no=1,
            interval=500,
            num_thread=1
        )
        
        mock_editer_class.assert_called_once_with(
            root_path="./out",
            book_no="1234",
            volume_no=1,
            interval=500,
            num_thread=1
        )
        mock_editer_instance.__enter__.assert_called_once()
        mock_editer_instance.__exit__.assert_called_once()


if __name__ == '__main__':
    unittest.main()

