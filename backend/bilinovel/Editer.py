#!/usr/bin/python
# -*- coding:utf-8 -*-
"""Novel download + EPUB generation engine."""

from __future__ import annotations

import os
import re
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
import zhconv

import requests
from bs4 import BeautifulSoup
from PIL import Image
from rich.progress import track as tqdm

from backend.browser_utils import create_browser
from backend.bilinovel.utils import (
    check_chars,
    get_container_html,
    get_content_html,
    get_cover_html,
    get_toc_html,
    replace_rubbish_text,
    text2htmls,
)

lock = threading.RLock()


class Editer:
    def __init__(
        self,
        root_path: str,
        book_no: str = "0000",
        volume_no: int = 1,
        interval: int = 0,
        num_thread: int = 1,
    ):
        self.book_no = book_no
        self.url_head = "https://www.linovelib.com"
        self.header = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/87.0.4280.67 Safari/537.36 Edg/87.0.664.47"
            ),
            "referer": self.url_head,
            "cookie": "night=1",
        }

        self.interval = float(interval) / 1000
        self.main_page = f"{self.url_head}/novel/{book_no}.html"
        self.cata_page = f"{self.url_head}/novel/{book_no}/catalog"
        self.read_tool_page = f"{self.url_head}/themes/zhmb/js/readtool.js"
        self.color_chap_name = "插图"
        self.color_page_name = "彩页"
        self.html_buffer: dict[str, bytes] = {}

        browser = create_browser()
        self.tab = browser.latest_tab

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

    def convert_text(self, text: str) -> str:
        if not hasattr(self, "conversion_mode"):
            self.conversion_mode = "traditional"  # Default fallback
            db_path = Path(__file__).resolve().parent.parent.parent / "bili-config.db"
            conn = None
            try:
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT VALUE FROM config WHERE KEY = 'conversion_mode'")
                row = cursor.fetchone()
                if row:
                    self.conversion_mode = row[0]
            except Exception as e:
                print(f"Error querying conversion_mode from db: {e}")
            finally:
                if conn:
                    conn.close()

        if not text:
            return text

        if self.conversion_mode == "traditional":
            return zhconv.convert(text, "zh-hant")
        elif self.conversion_mode == "simplified":
            return zhconv.convert(text, "zh-hans")
        else:
            return text

    def get_html(self, url: str, is_gbk: bool = False, is_main_text: bool = False) -> str:
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

        if is_main_text:
            bf = BeautifulSoup(req, "html.parser")
            p_eles = self.tab.eles("tag:p")
            for p in p_eles:
                if p.style(style="display") == "none":
                    all_attrs = p.attrs
                    class_key = None
                    class_value = None
                    for key in all_attrs.keys():
                        if "data-" in key:
                            class_key = key
                            class_value = all_attrs[class_key]
                    if class_key is not None:
                        p_elements_to_remove = bf.find_all("p", {class_key: class_value})
                        for p in p_elements_to_remove:
                            p.decompose()

            p_tags = bf.find_all("p")
            for p in p_tags:
                all_attrs = p.attrs
                keys_to_delete = [key for key in all_attrs.keys() if "data-" in key]
                for key in keys_to_delete:
                    del p[key]

            req = str(bf)

        if self.interval > 0:
            time.sleep(self.interval)
        return req

    def get_html_content(self, url: str, is_buffer: bool = False) -> bytes:
        if is_buffer:
            while url not in self.html_buffer:
                time.sleep(0.1)
        if url in self.html_buffer:
            return self.html_buffer[url]
        while True:
            try:
                req = requests.get(url, headers=self.header)
                break
            except Exception:
                pass
        lock.acquire()
        self.html_buffer[url] = req.content
        lock.release()
        return req.content

    def get_meta_data(self, main_html: str) -> None:
        bf = BeautifulSoup(main_html, "html.parser")
        self.book_name_raw = bf.find("meta", {"property": "og:novel:book_name"})["content"]
        self.book_name = self.convert_text(self.book_name_raw)
        self.author = self.convert_text(bf.find("meta", {"property": "og:novel:author"})["content"])

        brief = bf.find("div", {"class": "book-dec Jbook-dec"})
        brief_to_delete = brief.find("div")
        if brief_to_delete is not None:
            brief_to_delete.extract()
        self.brief = self.convert_text(brief.find_all("p")[0].text)

        book_meta = bf.find("div", class_="book-label")
        self.publisher = self.convert_text(book_meta.find("a", class_="label").text)
        span_tag = book_meta.find("span")
        self.tag_list = []
        if span_tag:
            for a_tag in span_tag.find_all("a"):
                self.tag_list.append(self.convert_text(a_tag.text))

        try:
            self.cover_url_back = re.search(
                r'src="(.*?)"', str(bf.find("div", {"class": "book-img fl"}))
            ).group(1)
        except Exception:
            self.cover_url_back = "cid"

    def make_folder(self) -> None:
        self.text_path = self.temp_path / "OEBPS" / "Text"
        self.img_path = self.temp_path / "OEBPS" / "Images"
        self.text_path.mkdir(parents=True, exist_ok=True)
        self.img_path.mkdir(parents=True, exist_ok=True)

    def get_index_url(self) -> bool:
        self.volume = {"chap_urls": [], "chap_names": [], "volume_name": ""}
        chap_html_list = self.get_chap_list(is_print=False)
        if len(chap_html_list) < self.volume_no:
            print("输入卷号超过实际卷数！")
            return False
        volume_array = self.volume_no - 1
        chap_html = chap_html_list[volume_array]

        volume_name = chap_html.find("h2", {"class": "v-line"}).text
        volume_name = volume_name.replace(f"{self.book_name_raw} ", "")
        volume_name = volume_name.replace(f"{self.book_name} ", "")
        self.volume["volume_name"] = self.convert_text(volume_name)
        chap_list = chap_html.find_all("li", {"class", "col-4"})
        for chap_html in chap_list:
            self.volume["chap_names"].append(self.convert_text(chap_html.text))
            self.volume["chap_urls"].append(
                self.url_head + chap_html.find("a").get("href")
            )
        return True

    def get_chap_list(self, is_print: bool = True) -> Optional[list]:
        cata_html = self.get_html(self.cata_page, is_gbk=False)
        bf = BeautifulSoup(cata_html, "html.parser")
        chap_html_list = bf.find_all("div", {"class", "volume clearfix"})
        if is_print:
            for chap_no, chap_html in enumerate(chap_html_list):
                print(f"[{chap_no + 1}]", chap_html.find("h2", {"class": "v-line"}).text)
            return None
        return chap_html_list

    def get_page_text(self, content_html: str) -> str:
        is_transfer_rubbish_code = "woff2" in content_html
        bf = BeautifulSoup(content_html, "html.parser")
        text_with_head = bf.find("div", {"id": "TextContent"})

        self.remove_element(text_with_head, id="show-more-images")
        self.remove_element(text_with_head, class_="google-auto-placed ap_container")
        self.remove_element(text_with_head, class_="dag")
        self.remove_element(text_with_head, id="hidden-images")
        text_html = str(text_with_head)

        pattern = re.compile(r"<!--(.*?)-->", re.DOTALL)
        text_html = pattern.sub("", text_html)

        img_urlre_list = re.findall(r"<img .*?>", text_html)
        for img_urlre in img_urlre_list:
            img_url_full = re.search(r".[a-zA-Z]{3}/(.*?).(jpg|png|jpeg)", img_urlre)
            img_url_name = img_url_full.group(1)
            img_url_tail = img_url_full.group(0).split(".")[-1]
            img_url = f"https://img3.readpai.com/{img_url_name}.{img_url_tail}"

            if img_url not in self.img_url_map:
                self.img_url_map[img_url] = str(len(self.img_url_map)).zfill(2)
            img_symbol = f'  <img alt="{self.img_url_map[img_url]}" src="../Images/{self.img_url_map[img_url]}.jpg"/>\n'
            if "00" in img_symbol:
                text_html = text_html.replace(img_urlre, "")
            else:
                text_html = text_html.replace(img_urlre, img_symbol)
                symbol_index = text_html.index(img_symbol)
                if text_html[symbol_index - 1] != "\n":
                    text_html = text_html[:symbol_index] + "\n" + text_html[symbol_index:]

        text = BeautifulSoup(text_html, "html.parser").find("div", id="TextContent")

        match = re.findall(r"<p(\d+)>", str(text))
        if len(match) > 0:
            warn_element = text.find(f"p{match[0]}")
            warn_element.decompose()

        text = text.decode_contents()
        if text.startswith("\n"):
            text = text[1:]
        if text.endswith("\n\n"):
            text = text[:-1]

        msg = "<br/><br/><br/>————————————以下为告示，读者请无视——————————————<p>"
        text = text[: text.find(msg)]

        if is_transfer_rubbish_code:
            text = replace_rubbish_text(text)
        return text

    @staticmethod
    def remove_element(bf_item, id=None, class_=None) -> None:
        if id is not None:
            remove_list = bf_item.find_all(id=id)
        elif class_ is not None:
            remove_list = bf_item.find_all(class_=class_)
        else:
            return
        for remove_element in remove_list:
            remove_element.decompose()

    def get_chap_text(
        self, url: str, chap_name: str, return_next_chapter: bool = False
    ) -> tuple[str, Optional[str]]:
        text_chap = ""
        page_no = 1
        url_ori = url
        next_chap_url = None
        while True:
            if page_no == 1:
                str_out = chap_name
            else:
                str_out = f"    正在下载第{page_no}页......"
            print(str_out)
            content_html = self.get_html(url, is_gbk=False, is_main_text=True)
            text = self.get_page_text(content_html)
            text_chap += text
            url_new = url_ori.replace(".html", f"_{page_no + 1}.html")[
                len(self.url_head) :
            ]
            if url_new in content_html:
                page_no += 1
                url = self.url_head + url_new
            else:
                if return_next_chapter:
                    next_chap_url = self.url_head + re.search(
                        r'书签</a><a href="(.*?)">下一页</a>', content_html
                    ).group(1)
                break
        return text_chap, next_chap_url

    def get_text(self) -> None:
        self.make_folder()
        repeat_img_strs: list[str] = []
        text_no = 0
        for chap_no, (chap_name, chap_url) in enumerate(
            zip(self.volume["chap_names"], self.volume["chap_urls"])
        ):
            is_fix_next_chap_url = chap_name in self.missing_last_chap_list
            text, next_chap_url = self.get_chap_text(
                chap_url, chap_name, return_next_chapter=is_fix_next_chap_url
            )
            text = self.convert_text(text)

            if chap_name == self.color_chap_name:
                text_html_color = text2htmls(self.color_page_name, text)
            else:
                file_name = self.text_path / f"{str(text_no).zfill(2)}.xhtml"
                text_html = text2htmls(chap_name, text)
                text_no += 1
                file_name.write_text(text_html, encoding="utf-8")
                repeat_img_strs += re.findall(
                    r'<img alt="[^"]*" src="../Images/\d+.jpg"/>', text_html
                )

            if is_fix_next_chap_url:
                self.volume["chap_urls"][chap_no + 1] = next_chap_url

        if self.is_color_page:
            text_html_color_new = []
            textfile = self.text_path / "color.xhtml"
            for img_line in repeat_img_strs:
                if img_line in text_html_color:
                    text_html_color = text_html_color.replace(img_line + "\n", "")
            textfile.write_text(text_html_color, encoding="utf-8")

    def get_image(self, is_gui: bool = False, signal=None) -> None:
        for url in self.img_url_map:
            self.pool.submit(self.get_html_content, url)
        img_path = self.img_path
        if is_gui:
            from backend.server import session
            len_iter = len(self.img_url_map.items())
            session.set_progress(0)
            for i, (img_url, img_name) in enumerate(self.img_url_map.items()):
                content = self.get_html_content(img_url, is_buffer=True)
                (img_path / f"{img_name}.jpg").write_bytes(content)
                session.set_progress(int(100 * (i + 1) / len_iter))
        else:
            for img_url, img_name in tqdm(self.img_url_map.items()):
                content = self.get_html_content(img_url)
                (img_path / f"{img_name}.jpg").write_bytes(content)

    def get_cover(self, is_gui: bool = False, signal=None) -> None:
        img_w, img_h = 300, 300
        try:
            imgfile = self.img_path / "00.jpg"
            img = Image.open(str(imgfile))
            img_w, img_h = img.size
            signal_msg = (str(imgfile), img_h, img_w)
            if is_gui:
                signal.emit(signal_msg)
        except Exception as e:
            print(e)
            print("没有封面图片，请自行用第三方EPUB编辑器手动添加封面")
        (self.text_path / "cover.xhtml").write_text(
            get_cover_html(img_w, img_h), encoding="utf-8"
        )

    def check_volume(self, is_gui: bool = False, signal=None, editline=None) -> None:
        self.color_chap_name = self.convert_text(self.color_chap_name)
        self.color_page_name = self.convert_text(self.color_page_name)
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
                        self.missing_last_chap_list.append(chap_names[chap_no - 1])

        if self.color_chap_name not in self.volume["chap_names"]:
            self.color_chap_name = self.convert_text(self.hand_in_color_page_name(
                is_gui, signal, editline
            ))
        self.volume["color_chap_name"] = self.color_chap_name

        if self.color_chap_name == "":
            self.is_color_page = False
            if not self.check_url(self.cover_url_back):
                self.img_url_map[self.cover_url_back] = str(
                    len(self.img_url_map)
                ).zfill(2)
                print("**************")
                print("提示：没有彩页，但主页封面存在，将使用主页的封面图片作为本卷图书封面")
                print("**************")

    @staticmethod
    def check_url(url: str) -> bool:
        return "javascript" in url or "cid" in url

    def get_prev_url(self, chap_no: int) -> str:
        content_html = self.get_html(
            self.volume["chap_urls"][chap_no], is_gbk=False, is_main_text=True
        )
        next_url = self.url_head + re.search(
            r'<div class="mlfy_page"><a href="(.*?)">上一页</a>', content_html
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

    @staticmethod
    def hand_in_msg(
        error_msg: str = "", is_gui: bool = False, signal=None, editline=None
    ) -> str:
        if is_gui:
            # Call FastAPI server session blocking prompt instead of PyQt GUI
            from backend.server import session
            content = session.request_input(error_msg)
        else:
            content = input(error_msg)
        return content

    def hand_in_url(
        self, chap_name: str, is_gui: bool = False, signal=None, editline=None
    ) -> str:
        error_msg = f'章节"{chap_name}"连接失效，请手动输入该章节链接(手机版"{self.url_head}"开头的链接):'
        return self.hand_in_msg(error_msg, is_gui, signal, editline)

    def hand_in_color_page_name(
        self, is_gui: bool = False, signal=None, editline=None
    ) -> str:
        if is_gui:
            error_msg = "插图页面不存在，需要下拉选择插图页标题，若不需要插图页则保持本栏为空直接点确定："
            editline.addItems(self.volume["chap_names"])
            editline.setCurrentIndex(-1)
        else:
            error_msg = "插图页面不存在，需要手动输入插图页标题，若不需要插图页则不输入直接回车："
        return self.hand_in_msg(error_msg, is_gui, signal, editline)

    def get_toc(self) -> None:
        if self.is_color_page:
            ind = self.volume["chap_names"].index(self.color_chap_name)
            self.volume["chap_names"].pop(ind)
        toc_htmls = get_toc_html(self.book_name, self.volume["chap_names"])
        (self.temp_path / "OEBPS" / "toc.ncx").write_text(toc_htmls, encoding="utf-8")

    def get_content(self) -> None:
        content_html = get_content_html(
            self.book_name,
            self.volume["volume_name"],
            self.volume_no,
            self.author,
            self.publisher,
            self.brief,
            self.tag_list,
            len(self.volume["chap_names"]),
            len(os.listdir(self.img_path)),
            self.is_color_page,
        )
        (self.temp_path / "OEBPS" / "content.opf").write_text(
            content_html, encoding="utf-8"
        )

    def get_epub_head(self) -> None:
        metainf_folder = self.temp_path / "META-INF"
        metainf_folder.mkdir(exist_ok=True)
        (metainf_folder / "container.xml").write_text(
            get_container_html(), encoding="utf-8"
        )
        (self.temp_path / "mimetype").write_text("application/epub+zip")

    def get_epub(self) -> str:
        import shutil
        import sqlite3
        from datetime import datetime

        # Build book subdirectory: out/書名/
        safe_book_name = check_chars(self.book_name)
        book_dir = self.epub_path / safe_book_name
        book_dir.mkdir(parents=True, exist_ok=True)

        # Filename: 書名 第X卷.epub
        safe_volume_name = check_chars(self.volume['volume_name'])
        epub_name = f"{safe_book_name} {safe_volume_name}"
        epub_file = book_dir / f"{epub_name}.epub"

        # Cache for in-app reader: out/書名/.library/bookno_volno/
        cache_path = book_dir / ".library" / f"{self.book_no}_{self.volume_no}"
        if cache_path.exists():
            shutil.rmtree(cache_path)
        
        # Copy unpacked files before zip compression
        shutil.copytree(self.temp_path / "OEBPS", cache_path / "OEBPS")
        
        with zipfile.ZipFile(str(epub_file), "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath_str, _, filenames in os.walk(self.temp_path):
                dirpath = Path(dirpath_str)
                fpath = str(dirpath.relative_to(self.temp_path))
                if fpath == ".":
                    fpath = ""
                for filename in filenames:
                    zf.write(str(dirpath / filename), f"{fpath}/{filename}" if fpath else filename)
                    
        # Register in SQLite database
        conn = None
        try:
            db_path = Path(__file__).resolve().parent.parent.parent / "bili-config.db"
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO shelf 
                (book_id, volume_id, title, volume_name, author, publisher, cover_path, epub_path, cache_path, download_date) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.book_no,
                self.volume_no,
                self.book_name,
                self.volume['volume_name'],
                self.author,
                self.publisher,
                str(cache_path / "OEBPS" / "Images" / "00.jpg"),
                str(epub_file),
                str(cache_path),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
        except Exception as e:
            print(f"Failed to record book in shelf db: {e}")
        finally:
            if conn:
                conn.close()
                
        self.temp_path_io.cleanup()
        return str(epub_file)
