"""Novel download orchestrator and router."""

from __future__ import annotations

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
    print("未输入卷号，将返回书籍目录信息......")
    with Editer(root_path="./out", book_no=book_no) as editer:
        print("--------------------------------")
        print(editer.book_name, editer.author)
        print("--------------------------------")
        editer.get_chap_list()
        print("--------------------------------")
        print("请输入所需要的卷号进行下载。")


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
        print("正在积极地获取书籍信息....")
        success = editer.get_index_url()
        if not success:
            print("书籍信息获取失败")
            return
        print(f"{editer.book_name}-{editer.volume['volume_name']}", editer.author)
        print("****************************")
        editer.check_volume(is_gui=is_gui, signal=hang_signal, editline=edit_line_hang)
        print("正在下载文本....")
        print("*********************")
        editer.get_text()
        print("*********************")

        print("正在下载插图.....................................")
        editer.get_image(is_gui=is_gui, signal=progressring_signal)

        print("正在编辑元数据....")
        editer.get_cover(is_gui=is_gui, signal=cover_signal)
        editer.get_toc()
        editer.get_content()
        editer.get_epub_head()

        print("正在生成电子书....")
        epub_file = editer.get_epub()
        print(f"生成成功！电子书路径【{epub_file}】")


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
) -> None:
    if not book_no:
        print("请检查输入是否完整正确！")
        return

    try:
        parsed = parse_volume_input(volume_no)
    except ValueError:
        print("请检查输入是否完整正确！")
        return

    if parsed is None:
        query_chaps(book_no)
        return

    if isinstance(parsed, int):
        download_single_volume(
            root_path, book_no, parsed, interval, num_thread,
            is_gui, hang_signal, progressring_signal, cover_signal, edit_line_hang,
        )
    else:
        for vol in parsed:
            download_single_volume(
                root_path, book_no, vol, interval, num_thread,
                is_gui, hang_signal, progressring_signal, cover_signal, edit_line_hang,
            )
        print("所有下载任务都已经完成！")
