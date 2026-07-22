import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from server.bilinovel.Editer import Editer

class TestBrowserLifecycle(unittest.TestCase):
    @patch('server.bilinovel.Editer.create_browser')
    @patch('server.bilinovel.Editer.Editer.get_html')
    @patch('server.bilinovel.Editer.Editer.get_meta_data')
    def test_browser_closed_on_success(self, mock_meta, mock_get_html, mock_create_browser):
        mock_browser = MagicMock()
        mock_create_browser.return_value = mock_browser
        
        with Editer(root_path="./out", book_no="1234") as editer:
            self.assertEqual(editer.browser, mock_browser)
        
        # Verify browser quit was called when exiting context manager
        mock_browser.quit.assert_called_once()

    @patch('server.bilinovel.Editer.create_browser')
    @patch('server.bilinovel.Editer.Editer.get_html')
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

    @patch('server.bilinovel.bilinovel_router.Editer')
    def test_query_chaps_context_manager(self, mock_editer_class):
        mock_editer_instance = MagicMock()
        mock_editer_class.return_value = mock_editer_instance
        
        from server.bilinovel.bilinovel_router import query_chaps
        query_chaps("1234")
        
        # Verify it was used as a context manager
        mock_editer_class.assert_called_once_with(root_path="./out", book_no="1234")
        mock_editer_instance.__enter__.assert_called_once()
        mock_editer_instance.__exit__.assert_called_once()

    @patch('server.bilinovel.bilinovel_router.Editer')
    def test_download_single_volume_context_manager(self, mock_editer_class):
        mock_editer_instance = MagicMock()
        mock_editer_instance.__enter__.return_value = mock_editer_instance
        # Ensure success = editer.get_index_url() returns True so it completes
        mock_editer_instance.get_index_url.return_value = True
        mock_editer_class.return_value = mock_editer_instance
        
        # Set up some attributes that are accessed
        mock_editer_instance.book_name = "Test Book"
        mock_editer_instance.author = "Test Author"
        mock_editer_instance.volume = {"volume_name": "Vol 1"}

        with tempfile.TemporaryDirectory() as directory:
            epub_path = Path(directory) / "Test Book Vol 1.epub"
            epub_path.write_bytes(b"test epub")
            mock_editer_instance.get_epub.return_value = str(epub_path)

            from server.bilinovel.bilinovel_router import download_single_volume
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

    @patch('server.bilinovel.bilinovel_router.Editer')
    def test_download_single_volume_rejects_missing_epub(self, mock_editer_class):
        editer = MagicMock()
        editer.__enter__.return_value = editer
        editer.get_index_url.return_value = True
        editer.book_name = "Test Book"
        editer.author = "Test Author"
        editer.volume = {"volume_name": "Vol 1"}
        editer.get_epub.return_value = None
        mock_editer_class.return_value = editer

        from server.bilinovel.bilinovel_router import download_single_volume

        with self.assertRaisesRegex(RuntimeError, "returned no saved file"):
            download_single_volume(
                root_path="./out",
                book_no="1234",
                volume_no=1,
                interval=500,
                num_thread=1,
            )

    @patch('server.bilinovel.Editer.create_browser')
    @patch('server.bilinovel.Editer.Editer.get_html')
    @patch('server.bilinovel.Editer.Editer.get_meta_data')
    @patch('server.bilinovel.Editer.ThreadPoolExecutor')
    @patch('server.bilinovel.Editer.tempfile.TemporaryDirectory')
    def test_close_cleanup(self, mock_temp_dir, mock_executor, mock_meta, mock_get_html, mock_create_browser):
        mock_browser = MagicMock()
        mock_create_browser.return_value = mock_browser
        
        mock_pool = MagicMock()
        mock_executor.return_value = mock_pool
        
        mock_temp = MagicMock()
        mock_temp.name = "/fake/temp/path"
        mock_temp_dir.return_value = mock_temp
        
        editer = Editer(root_path="./out", book_no="1234")
        
        # Verify they are assigned
        self.assertEqual(editer.pool, mock_pool)
        self.assertEqual(editer.temp_path_io, mock_temp)
        
        # Call close
        editer.close()
        
        # Verify both shutdown and cleanup were called
        mock_pool.shutdown.assert_called_once()
        mock_temp.cleanup.assert_called_once()
        
        # Verify safety guards set them to None
        self.assertIsNone(editer.pool)
        self.assertIsNone(editer.temp_path_io)


if __name__ == '__main__':
    unittest.main()
