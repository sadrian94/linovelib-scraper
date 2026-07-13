#!/usr/bin/python
# -*- coding:utf-8 -*-
"""Manga chapter/image downloader."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from rich.progress import track as tqdm

from backend.browser_utils import create_browser
from backend.bilinovel.utils import check_chars
from .utils import convert_avif_to_jpg

lock = threading.RLock()


class Downloader:
    def __init__(
        self,
        root_path: str,
        head: str = "https://www.bilicomic.net",
        book_no: str = "0000",
        volume_no: int = 1,
        interval: int = 0,
        color_page: str = "0",
    ):
        self.header = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/87.0.4280.67 Safari/537.36 Edg/87.0.664.47"
            ),
            "referer": head,
            "cookie": "night=1",
        }

        self.url_head = head
        self.interval = float(interval) / 1000
        self.color_page = int(color_page)
        self.main_page = f"{self.url_head}/detail/{book_no}.html"
        self.cata_page = f"{self.url_head}/read/{book_no}/catalog"
        self.read_tool_page = f"{self.url_head}/themes/zhmb/js/readtool.js"
        self.color_page_name = "彩页"
        self.html_buffer: dict[str, bytes] = {}

        browser = create_browser()
        self.tab = browser.latest_tab

        main_html = self.get_html(self.main_page)
        self.get_meta_data(main_html)

        self.img_url_map: dict[str, str] = {}
        self.volume_no = volume_no

        self.epub_path = Path(root_path)
        self.comic_path = (
            self.epub_path / f"{check_chars(self.book_name)}_{volume_no}"
        )
        self.temp_path_io = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_path_io.name)

        self.missing_last_chap_list: list[str] = []
        self.is_color_page = True
        self.page_url_map: dict = {}
        self.ignore_urls: list = []
        self.url_buffer: list = []
        self.max_thread_num = 8
        self.pool = ThreadPoolExecutor(1)

    def get_html(self, url: str, is_gbk: bool = False) -> str:
        while True:
            self.tab.get(url)
            req = self.tab.html
            while (
                "<title>Access denied | www.linovelib.com used Cloudflare to restrict access</title>"
                in req
            ):
                print("下载频繁，触发反爬，5秒后重试....")
                time.sleep(5)
                self.tab.get(url)
                req = self.tab.html
            if is_gbk:
                req.encoding = "GBK"
            break
        return req

    def get_meta_data(self, main_html: str) -> None:
        bf = BeautifulSoup(main_html, "html.parser")
        self.book_name = bf.find("h1", class_="book-title").text
        self.author = bf.find("span", class_="authorname").text
        self.brief = bf.find("section", id="bookSummary").text.replace("\n", "")

        book_meta = bf.find("span", class_="tag-small-group")
        self.tag_list = []
        if book_meta:
            for a_tag in book_meta.find_all("a"):
                self.tag_list.append(a_tag.text)

    def make_folder(self) -> None:
        self.comic_path.mkdir(parents=True, exist_ok=True)
        self.text_path = self.comic_path / "OEBPS" / "Text"
        self.img_path = self.comic_path / "OEBPS" / "Images"
        self.text_path.mkdir(parents=True, exist_ok=True)
        self.img_path.mkdir(parents=True, exist_ok=True)

    def get_index_url(self) -> bool:
        self.volume = {"chap_urls": [], "chap_names": [], "volume_name": ""}
        chap_html_list = self.get_chap_list(is_print=False)
        if chap_html_list is None or len(chap_html_list) < self.volume_no:
            print("输入卷号超过实际卷数！")
            return False
        volume_array = self.volume_no - 1
        chap_html = chap_html_list[volume_array]

        self.volume["volume_name"] = chap_html.find("h3").text
        chap_list = chap_html.find_all("li", {"class", "chapter-li jsChapter"})
        for chap_html in chap_list:
            chap_name = chap_html.find("span").text
            self.volume["chap_names"].append(chap_name)
            self.volume["chap_urls"].append(
                self.url_head + chap_html.find("a").get("href")
            )
        return True

    def get_chap_list(self, is_print: bool = True) -> Optional[list]:
        cata_html = self.get_html(self.cata_page, is_gbk=False)
        bf = BeautifulSoup(cata_html, "html.parser")
        chap_html_list = bf.find_all("div", class_="catalog-volume")
        if is_print:
            for chap_no, chap_html in enumerate(chap_html_list):
                print(f"[{chap_no + 1}]", chap_html.find("h3").text)
            return None
        return chap_html_list

    def get_manga(self, is_gui: bool = False, signal=None) -> None:
        for chap_no, (chap_name, chap_url) in enumerate(
            zip(self.volume["chap_names"], self.volume["chap_urls"])
        ):
            print(chap_name)
            self.get_html(chap_url)

            is_color_page = self.color_page > 0 and chap_no == 0
            self.get_chap_image(chap_no, chap_name, is_gui, signal, is_color_page)
            is_fix_next_chap_url = chap_name in self.missing_last_chap_list
            if is_fix_next_chap_url:
                chap_html = self.get_html(chap_url)
                next_chap_url = self.url_head + re.search(
                    r"url_next:\'(.*?)\',", chap_html
                ).group(1)
                self.volume["chap_urls"][chap_no + 1] = next_chap_url
        if self.color_page > 1:
            self.volume["chap_names"] = [self.color_page_name] + self.volume[
                "chap_names"
            ]
        self.temp_path_io.cleanup()

    def get_chap_image(
        self,
        chap_no: int,
        chap_name: str,
        is_gui: bool = False,
        signal=None,
        is_color_page: bool = False,
    ) -> None:
        save_path = self.comic_path / check_chars(chap_name)
        save_path.mkdir(exist_ok=True)
        chap_html = BeautifulSoup(self.tab.html, "html.parser")
        img_elements = chap_html.find_all("img", class_="imagecontent")
        img_url_list = [
            img_element.get("data-src") for img_element in img_elements
        ]

        if chap_no == 0:
            self.get_single_image(
                img_url_list[0], str(self.comic_path), "cover.avif"
            )

        if is_color_page:
            if self.color_page > 1:
                img_url_list_color = img_url_list[1 : self.color_page]
                save_path_color = self.comic_path / self.color_page_name
                save_path_color.mkdir(exist_ok=True)
                if len(os.listdir(save_path_color)) != len(img_url_list_color):
                    self.clear_dir(save_path_color)
                    for i, img_url in enumerate(img_url_list_color):
                        self.get_single_image(
                            img_url,
                            str(save_path_color),
                            f"{str(i).zfill(3)}.avif",
                        )
            img_url_list = img_url_list[self.color_page :]

        if is_gui:
            len_iter = len(img_elements)
            signal.emit("start")
            if len(os.listdir(save_path)) != len(img_url_list):
                self.clear_dir(save_path)
                for i, img_url in enumerate(img_url_list):
                    self.get_single_image(
                        img_url, str(save_path), f"{str(i).zfill(3)}.avif"
                    )
                    signal.emit(int(100 * (i + 1) / len_iter))
            signal.emit("end")
        else:
            if len(os.listdir(save_path)) != len(img_url_list):
                self.clear_dir(save_path)
                for i, img_url in enumerate(tqdm(img_url_list)):
                    self.get_single_image(
                        img_url, str(save_path), f"{str(i).zfill(3)}.avif"
                    )

    def get_single_image(
        self, img_url: str, save_path: str, save_name: str
    ) -> None:
        img_element = self.tab.ele(f"@@tag()=img@@data-src={img_url}")
        while img_element.attrs["class"] == "imagecontent lazyload":
            self.tab.scroll.to_see(img_element)
            time.sleep(0.1)
            img_element = self.tab.ele(f"@@tag()=img@@data-src={img_url}")
        try:
            img_element.save(str(self.temp_path), save_name, rename=False)
            convert_avif_to_jpg(
                str(self.temp_path / save_name),
                str(Path(save_path) / save_name.replace(".avif", ".jpg")),
            )
            (self.temp_path / save_name).unlink()
        except Exception as error:
            print(error)
            self.tab.refresh()
            self.get_single_image(img_url, save_path, save_name)

    @staticmethod
    def clear_dir(path: Path) -> None:
        for filename in os.listdir(path):
            file_path = path / filename
            try:
                if file_path.is_file() or file_path.is_symlink():
                    file_path.unlink()
                elif file_path.is_dir():
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")

    @staticmethod
    def check_url(url: str) -> bool:
        return "javascript" in url or "cid" in url

    def get_prev_url(self, chap_no: int) -> str:
        content_html = self.get_html(
            self.volume["chap_urls"][chap_no], is_gbk=False
        )
        next_url = self.url_head + re.search(
            r"url_previous:\'(.*?)\',", content_html
        ).group(1)
        return next_url

    def prev_fix_url(self, chap_no: int, chap_num: int) -> bool:
        if chap_no == chap_num - 1:
            return False
        elif self.check_url(self.volume["chap_urls"][chap_no + 1]):
            if self.prev_fix_url(chap_no + 1, chap_num):
                self.volume["chap_urls"][chap_no] = self.get_prev_url(chap_no + 1)
                return True
            return False
        else:
            self.volume["chap_urls"][chap_no] = self.get_prev_url(chap_no + 1)
            return True

    def check_volume(
        self, is_gui: bool = False, signal=None, editline=None
    ) -> None:
        chap_names = self.volume["chap_names"]
        chap_num = len(self.volume["chap_names"])
        for chap_no, url in enumerate(self.volume["chap_urls"]):
            if self.check_url(url):
                if not self.prev_fix_url(chap_no, chap_num):
                    if chap_no == 0:
                        self.volume["chap_urls"][0] = self.hand_in_url(
                            chap_names[chap_no], is_gui, signal, editline
                        )
                    else:
                        self.missing_last_chap_list.append(
                            chap_names[chap_no - 1]
                        )

    @staticmethod
    def hand_in_msg(
        error_msg: str = "", is_gui: bool = False, signal=None, editline=None
    ) -> str:
        if is_gui:
            print(error_msg)
            signal.emit("hang")
            time.sleep(1)
            while not editline.isHidden():
                time.sleep(1)
            content = editline.text()
            editline.clear()
        else:
            content = input(error_msg)
        return content

    def hand_in_url(
        self, chap_name: str, is_gui: bool = False, signal=None, editline=None
    ) -> str:
        error_msg = f'章节"{chap_name}"连接失效，请手动输入该章节链接(手机版"{self.url_head}"开头的链接):'
        return self.hand_in_msg(error_msg, is_gui, signal, editline)
