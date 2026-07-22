import tempfile
import unittest
from pathlib import Path

from server.app import resolve_shelf_path


class TestShelfPaths(unittest.TestCase):
    def test_rebases_legacy_windows_out_path_to_download_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            download_path = Path(temp_dir) / "downloads"
            epub_path = download_path / "Book" / "Volume 1.epub"
            epub_path.parent.mkdir(parents=True)
            epub_path.touch()

            resolved = resolve_shelf_path(r"out\Book\Volume 1.epub", download_path)

            self.assertEqual(resolved, epub_path.resolve())

    def test_returns_none_when_shelf_file_has_been_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            resolved = resolve_shelf_path("out/Book/missing.epub", Path(temp_dir))

            self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
