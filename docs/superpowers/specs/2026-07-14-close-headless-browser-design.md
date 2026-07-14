# Design Spec: Ensure Headless Browser Closes After Download / Query

**Date:** 2026-07-14
**Status:** Proposed

## Problem
Each run of the novel downloader/query launches a headless Chromium instance via DrissionPage. Currently, the browser instance is never closed (`browser.quit()` is not called). When downloading multiple volumes sequentially or performing queries, multiple Chromium processes leak, leading to significant performance degradation and high system resource usage.

## Proposed Solution: Option 1 (Context Manager / `with` statement)
We will implement Python's context manager protocol (`__enter__` and `__exit__`) on the `Editer` class. This ensures the Chromium browser is automatically shut down when control exits the `with` block, even if an exception is raised.

### Changes in `backend/bilinovel/Editer.py`
1. Store the browser object as `self.browser` in `__init__`.
2. Add a `close(self)` method to safely shut down the browser:
   ```python
   def close(self) -> None:
       if hasattr(self, "browser") and self.browser:
           try:
               self.browser.quit()
           except Exception as e:
               print(f"Error quitting browser: {e}")
           finally:
               self.browser = None
   ```
3. Add a destructor `__del__(self)` calling `self.close()` as a secondary safeguard.
4. Implement `__enter__(self) -> Editer` returning `self`.
5. Implement `__exit__(self, exc_type, exc_val, exc_tb) -> None` calling `self.close()`.

### Changes in `backend/bilinovel/bilinovel_router.py`
1. Update `query_chaps(book_no)` to instantiate `Editer` using a `with` statement:
   ```python
   with Editer(root_path="./out", book_no=book_no) as editer:
       ...
   ```
2. Update `download_single_volume(...)` to instantiate `Editer` using a `with` statement:
   ```python
   with Editer(
       root_path=root_path,
       book_no=book_no,
       volume_no=volume_no,
       interval=interval,
       num_thread=num_thread,
   ) as editer:
       ...
   ```

## Verification Plan
1. Start the backend server or run a CLI query/download.
2. Verify that Chromium processes are spawned.
3. Verify that Chromium processes are terminated immediately when the query finishes or after a volume download finishes.
4. Verify that Chromium processes are terminated even if the download task is aborted or encounters an error.
