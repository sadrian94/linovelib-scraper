"""Manga download orchestrator and router."""

from __future__ import annotations

from typing import Optional

from .Downloader import Downloader
from .Editer import Editer
from backend.router_utils import parse_volume_input


def query_chaps(book_no: str) -> None:
    print("未输入卷号，将返回书籍目录信息......")
    downloader = Downloader(root_path="./out", book_no=book_no)
    print("--------------------------------")
    print(downloader.book_name, downloader.author)
    print("--------------------------------")
    downloader.get_chap_list()
    print("--------------------------------")
    print("请输入所需要的卷号进行下载。")


def download_single_volume(
    root_path: str,
    book_no: str,
    volume_no: int,
    interval: int,
    color_page: str,
    is_gui: bool = False,
    hang_signal=None,
    progressring_signal=None,
    cover_signal=None,
    edit_line_hang=None,
) -> None:
    downloader = Downloader(
        root_path=root_path,
        book_no=book_no,
        volume_no=volume_no,
        interval=interval,
        color_page=color_page,
    )
    print("正在积极地获取书籍信息....")
    success = downloader.get_index_url()
    if not success:
        print("书籍信息获取失败")
        return
    print(f"{downloader.book_name}-{downloader.volume['volume_name']}", downloader.author)
    print("****************************")
    downloader.check_volume(is_gui=is_gui, signal=hang_signal, editline=edit_line_hang)
    print("正在下载漫画....")
    print("*********************")
    downloader.get_manga(is_gui=is_gui, signal=progressring_signal)
    print("*********************")
    chap_list = downloader.volume["chap_names"]
    editer = Editer(
        downloader.book_name,
        downloader.volume["volume_name"],
        downloader.volume_no,
        downloader.author,
        downloader.brief,
        downloader.tag_list,
        chap_list,
        downloader.comic_path,
        root_path,
        delete_comic=0,
    )
    editer.get_cover(is_gui=is_gui, signal=cover_signal)
    editer.pack_img()
    editer.typesetting()
    editer.get_epub()


def downloader_router(
    root_path: str,
    book_no: str,
    volume_no: str,
    interval: int = 5000,
    color_page: str = "0",
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
            root_path, book_no, parsed, interval, color_page,
            is_gui, hang_signal, progressring_signal, cover_signal, edit_line_hang,
        )
    else:
        for vol in parsed:
            download_single_volume(
                root_path, book_no, vol, interval, color_page,
                is_gui, hang_signal, progressring_signal, cover_signal, edit_line_hang,
            )
        print("所有下载任务都已经完成！")
