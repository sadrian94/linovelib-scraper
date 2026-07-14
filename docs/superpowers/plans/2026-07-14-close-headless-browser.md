# Ensure Headless Browser Closes After Download / Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure the headless Chromium browser started by DrissionPage is closed under all scenarios (success, error during run, or error during initialization) to avoid resource leaks.

**Architecture:** Implement the context manager protocol (`__enter__` and `__exit__`) and a destructor (`__del__`) on the `Editer` class. Wrap the initialization of `Editer` in `try...except` to clean up browser resources if initialization fails. Update calling entry points in `bilinovel_router.py` to use `with Editer(...) as editer:`.

**Tech Stack:** Python 3, unittest (standard library), unittest.mock

## Global Constraints

- Preserve all existing comments and docstrings.
- Ensure no external network calls are made during unit testing.
- The browser must be closed under all completion states (success or exception).

---

### Task 1: Create Unit Tests for Browser Lifecycle Management

**Files:**
- Create: `tests/test_browser_lifecycle.py`

**Interfaces:**
- Consumes: `backend.bilinovel.Editer` class

- [ ] **Step 1: Write the failing tests**

Create the test file `tests/test_browser_lifecycle.py` with mock tests verifying browser cleanup:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests/test_browser_lifecycle.py`
Expected: Failures (e.g. AttributeErrors or TypeErrors since context manager and cleanup methods are not implemented on `Editer` yet).

- [ ] **Step 3: Commit**

```bash
git add tests/test_browser_lifecycle.py
git commit -m "test: add browser lifecycle unit tests"
```

---

### Task 2: Implement Context Manager and Lifecycle Management in `Editer`

**Files:**
- Modify: `backend/bilinovel/Editer.py`

**Interfaces:**
- Produces: `Editer.__enter__`, `Editer.__exit__`, `Editer.close`, and `Editer.__del__`

- [ ] **Step 1: Modify `Editer.__init__` and implement methods**

In `backend/bilinovel/Editer.py`, modify line 66 to store `self.browser`. Wrap the rest of `__init__` in a `try...except` block, and implement `close()`, `__enter__`, `__exit__`, and `__del__`:

```python
        self.browser = create_browser()
        self.tab = self.browser.latest_tab

        try:
            main_html = self.get_html(self.main_page)
            self.get_meta_data(main_html)

            self.img_url_map: dict[str, str] = {}
            self.volume_no = volume_no

            self.epub_path = Path(root_path)
            self.temp_path_io = tempfile.TemporaryDirectory()
            self.temp_path = Path(self.temp_path_io.name)

            self.missing_last_chap_list: list[str] = []
            self.is_color_page = True
            self.page_url_map: dict = {}
            self.ignore_urls: list = []
            self.url_buffer: list = []
            self.max_thread_num = 8
            self.pool = ThreadPoolExecutor(int(num_thread))
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Close the browser instance."""
        if hasattr(self, "browser") and self.browser:
            try:
                self.browser.quit()
            except Exception as e:
                print(f"Error quitting browser: {e}")
            finally:
                self.browser = None

    def __enter__(self) -> Editer:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
```

- [ ] **Step 2: Run the unit test to verify it passes**

Run: `python -m unittest tests/test_browser_lifecycle.py`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/bilinovel/Editer.py
git commit -m "feat: implement context manager and close method in Editer"
```

---

### Task 3: Update Downloader Router to Use Context Manager

**Files:**
- Modify: `backend/bilinovel/bilinovel_router.py`

**Interfaces:**
- Consumes: Context manager of `Editer`

- [ ] **Step 1: Update `query_chaps` and `download_single_volume`**

In `backend/bilinovel/bilinovel_router.py`, update `query_chaps` and `download_single_volume` to use `with Editer(...) as editer:`:

For `query_chaps`:
```python
def query_chaps(book_no: str) -> None:
    print("未输入卷号，将返回書籍目錄信息......")
    with Editer(root_path="./out", book_no=book_no) as editer:
        print("--------------------------------")
        print(editer.book_name, editer.author)
        print("--------------------------------")
        editer.get_chap_list()
        print("--------------------------------")
        print("请输入所需要的卷号进行下载。")
```

For `download_single_volume`:
```python
def download_single_volume(
    root_path: str,
    book_no: str,
    volume_no: int,
    interval: int,
    num_thread: int,
    is_gui: bool = False,
    hang_signal=None,
    progressring_signal=None,
    cover_signal=None,
    edit_line_hang=None,
) -> None:
    with Editer(
        root_path=root_path,
        book_no=book_no,
        volume_no=volume_no,
        interval=interval,
        num_thread=num_thread,
    ) as editer:
        print("正在积极地获取書籍信息....")
        success = editer.get_index_url()
        if not success:
            print("書籍信息获取失敗")
            return
        print(f"{editer.book_name}-{editer.volume['volume_name']}", editer.author)
        print("****************************")
        editer.check_volume(is_gui=is_gui, signal=hang_signal, editline=edit_line_hang)
        print("正在下载文本....")
        print("*********************")
        editer.get_text()
        print("*********************")

        print("正在下载插圖.....................................")
        editer.get_image(is_gui=is_gui, signal=progressring_signal)

        print("正在編輯元數據....")
        editer.get_cover(is_gui=is_gui, signal=cover_signal)
        editer.get_toc()
        editer.get_content()
        editer.get_epub_head()

        print("正在生成電子書....")
        epub_file = editer.get_epub()
        print(f"生成成功！電子書路徑【{epub_file}】")
```

- [ ] **Step 2: Commit**

```bash
git add backend/bilinovel/bilinovel_router.py
git commit -m "feat: use context manager for Editer in bilinovel_router"
```
