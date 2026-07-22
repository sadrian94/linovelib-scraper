"""Novel download orchestrator and router."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .Editer import Editer


def parse_volume_input(volume_no: str) -> Optional[Union[int, list[int]]]:
    """Parse user volume input into a single int, list of ints, or None (query only)."""
    if not volume_no:
        return None
    if volume_no.isdigit():
        vol = int(volume_no)
        if vol <= 0:
            raise ValueError("Volume number must be positive")
        return vol
    if "-" in volume_no:
        parts = volume_no.split("-")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            start, end = int(parts[0]), int(parts[1])
            if 0 < start < end:
                return list(range(start, end + 1))
        raise ValueError("Invalid range format, use e.g. '1-3'")
    if "," in volume_no:
        parts = volume_no.split(",")
        if all(p.strip().isdigit() for p in parts):
            return [int(p.strip()) for p in parts]
        raise ValueError("Invalid comma list format, use e.g. '1,2,3'")
    raise ValueError("Invalid volume input")


def query_chaps(book_no: str) -> None:
    print("No volume number provided; returning the book catalog.")
    with Editer(root_path="./out", book_no=book_no) as editer:
        print("--------------------------------")
        print(editer.book_name, editer.author)
        print("--------------------------------")
        editer.get_chap_list()
        print("--------------------------------")
        print("Enter the volume number you want to download.")


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
) -> str:
    with Editer(
        root_path=root_path,
        book_no=book_no,
        volume_no=volume_no,
        interval=interval,
        num_thread=num_thread,
    ) as editer:
        print("Fetching book information...")
        success = editer.get_index_url()
        if not success:
            raise RuntimeError("Failed to fetch book information; no EPUB was created.")
        print(f"{editer.book_name}-{editer.volume['volume_name']}", editer.author)
        print("****************************")
        editer.check_volume(is_gui=is_gui, signal=hang_signal, editline=edit_line_hang)
        print("Downloading text...")
        print("*********************")
        editer.get_text()
        print("*********************")

        print("Downloading illustrations...")
        editer.get_image(is_gui=is_gui, signal=progressring_signal)

        print("Editing metadata...")
        editer.get_cover(is_gui=is_gui, signal=cover_signal)
        editer.get_toc()
        editer.get_content()
        editer.get_epub_head()

        print("Generating EPUB...")
        epub_file = editer.get_epub()
        if not isinstance(epub_file, str) or not epub_file or not Path(epub_file).is_file():
            raise RuntimeError("EPUB generation returned no saved file.")
        print(f"EPUB generated successfully: {epub_file}")
        return epub_file


def downloader_router(
    root_path: str,
    book_no: str,
    volume_no: str,
    interval: int = 500,
    num_thread: int = 1,
    is_gui: bool = False,
    hang_signal=None,
    progressring_signal=None,
    cover_signal=None,
    edit_line_hang=None,
) -> list[str]:
    if not book_no:
        raise ValueError("Book ID is required")

    try:
        parsed = parse_volume_input(volume_no)
    except ValueError:
        raise

    if parsed is None:
        query_chaps(book_no)
        return []

    if isinstance(parsed, int):
        return [download_single_volume(
            root_path, book_no, parsed, interval, num_thread,
            is_gui, hang_signal, progressring_signal, cover_signal, edit_line_hang,
        )]
    else:
        epub_files = []
        for vol in parsed:
            epub_files.append(download_single_volume(
                root_path, book_no, vol, interval, num_thread,
                is_gui, hang_signal, progressring_signal, cover_signal, edit_line_hang,
            ))
        print("All download tasks are complete.")
        return epub_files
