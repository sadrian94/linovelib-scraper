#!/usr/bin/python
# -*- coding:utf-8 -*-
"""Novel download + EPUB generation engine."""

from __future__ import annotations

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

from server.browser_utils import cleanup_browser_profile, create_browser
from server.bilinovel.epub_packer import Chapter, EpubPacker, JPEG, PNG, Resource
from server.bilinovel.utils import (
    check_chars,
    replace_rubbish_text,
    text2htmls,
)

lock = threading.RLock()

READER_VIEWPORT = (390, 844)
CHAPTER_READY_TIMEOUT_SECONDS = 15
CHAPTER_STABLE_POLLS = 6
CHAPTER_PENDING_RESTORE_POLLS = 4


class IncompleteChapterContentError(RuntimeError):
    """Raised when the source cannot provide a complete ordered chapter."""


class Editer:
    def __init__(
        self,
        root_path: str,
        book_no: str = "0000",
        volume_no: int = 1,
        interval: int = 0,
        num_thread: int = 1,
    ):
        self.browser = None
        self.tab = None
        self.book_no = book_no
        self.url_head = "https://www.linovelib.com"
        # The Taiwanese reader delivers complete chapter content to a narrow,
        # rendered viewport. The desktop host remains in use for metadata and
        # catalog parsing, whose markup this application already understands.
        self.reader_url_head = "https://tw.linovelib.com"
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

        try:
            self.browser = create_browser()
            self.tab = self.browser.latest_tab
            self.tab.set.window.size(*READER_VIEWPORT)
            main_html = self.get_html(self.main_page)
            self.get_meta_data(main_html)

            self.img_url_map: dict[str, str] = {}
            self.cover_image_name: Optional[str] = None
            # Catalog order is authoritative.  Downloads may be concurrent, but
            # EPUB spine and navigation are built from this list only.
            self.chapter_documents: list[tuple[str, str, bool]] = []
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
        """Close the browser instance, pool executor, and temporary directory."""
        if hasattr(self, "browser") and self.browser:
            try:
                self.browser.quit()
            except Exception as e:
                print(f"Error quitting browser: {e}")
            finally:
                cleanup_browser_profile(self.browser)
                self.browser = None

        if hasattr(self, "pool") and self.pool:
            try:
                self.pool.shutdown()
            except Exception as e:
                print(f"Error shutting down thread pool: {e}")
            finally:
                self.pool = None

        if hasattr(self, "temp_path_io") and self.temp_path_io:
            try:
                self.temp_path_io.cleanup()
            except Exception as e:
                print(f"Error cleaning up temporary directory: {e}")
            finally:
                self.temp_path_io = None

    def __enter__(self) -> Editer:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

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
                print("Rate limit detected; retrying in 5 seconds...")
                time.sleep(5)
                self.tab.get(url)
                req = self.tab.html
            if is_gbk:
                req.encoding = "GBK"
            if is_main_text:
                self._wait_for_complete_chapter(url)
                # ``tab.html`` can expose the navigation response before a
                # deferred chapterlog script has finished restoring paragraphs.
                # Take an explicit live-DOM snapshot after the stability check.
                req = self.tab.run_js("return document.documentElement.outerHTML;") or self.tab.html
            break

        if self.interval > 0:
            time.sleep(self.interval)
        return req

    def _wait_for_complete_chapter(self, url: str) -> None:
        """Wait until the live reader DOM has stopped being reordered.

        Linovelib's deferred ``chapterlog.js`` can permute existing ``<p>``
        elements without changing either total text length or child count.  A
        content fingerprint is therefore required; counting nodes alone races
        the anti-scraping restoration script and saves shuffled prose.
        """
        deadline = time.monotonic() + CHAPTER_READY_TIMEOUT_SECONDS
        stable_polls = 0
        pending_polls = 0
        previous_signature = None
        script = """
            const root = document.querySelector('#acontent');
            if (!root) return '';
            const html = root.innerHTML || '';
            const text = root.innerText || '';
            const failed = /內容加載失敗|内容加载失败/.test(text);
            let hash = 2166136261;
            for (let i = 0; i < html.length; i++) {
                hash ^= html.charCodeAt(i);
                hash = Math.imul(hash, 16777619);
            }
            const shuffleableParagraphs = Array.from(root.children).filter(
                node =>
                    node.tagName === 'P' &&
                    node.innerHTML.replace(/\\s+/g, '') !== ''
            ).length;
            // chapterlog only permutes paragraphs after the first twenty.
            // Short chapters (notably illustration pages) legitimately retain
            // the script tag but have no deferred work to wait for.
            const pending =
                shuffleableParagraphs > 20 &&
                Boolean(document.querySelector('script[src*="chapterlog.js"]')) &&
                !root.querySelector('p[data-k], p[data-bilinovel-restored]');
            return `${failed}|${text.length}|${root.children.length}|${hash >>> 0}|${pending}`;
        """

        while time.monotonic() < deadline:
            signature = self.tab.run_js(script)
            if signature:
                failed, text_length, child_count, _fingerprint, pending = signature.split("|", 4)
                if failed == "false" and pending == "true":
                    pending_polls += 1
                    if pending_polls >= CHAPTER_PENDING_RESTORE_POLLS:
                        if self._restore_pending_chapter_order():
                            return
                        pending_polls = 0
                else:
                    pending_polls = 0
                if failed == "false" and pending == "false" and int(text_length) > 40:
                    if signature == previous_signature:
                        stable_polls += 1
                        if stable_polls >= CHAPTER_STABLE_POLLS:
                            return
                    else:
                        stable_polls = 0
                        previous_signature = signature
            time.sleep(0.25)

        if self._restore_pending_chapter_order():
            return
        raise IncompleteChapterContentError(
            "The source did not provide stable, complete chapter content within "
            f"{CHAPTER_READY_TIMEOUT_SECONDS} seconds: {url}"
        )

    def _restore_pending_chapter_order(self) -> bool:
        """Restore a chapterlog-shuffled DOM if the page script never settles.

        The source only shuffles non-empty direct paragraph children after the
        first twenty.  Keep every other node in its original slot, matching the
        reference packer's restoration behaviour.
        """
        script = """
            return (() => {
                const root = document.querySelector('#acontent');
                if (!root || root.querySelector('p[data-k], p[data-bilinovel-restored]')) {
                    return false;
                }
                const source = document.documentElement.outerHTML;
                const chapterMatch = source.match(/chapterid\\s*:\\s*['"]?(\\d+)/i);
                if (!chapterMatch) return false;

                const nodes = Array.from(root.childNodes);
                const slots = [];
                const paragraphs = [];
                for (let index = 0; index < nodes.length; index++) {
                    const node = nodes[index];
                    if (
                        node.nodeType === Node.ELEMENT_NODE &&
                        node.tagName === 'P' &&
                        node.innerHTML.replace(/\\s+/g, '') !== ''
                    ) {
                        slots.push(index);
                        paragraphs.push(node);
                    }
                }
                if (paragraphs.length <= 20) return false;

                const indices = Array.from({ length: paragraphs.length }, (_, index) => index);
                let seed = Number(chapterMatch[1]) * 126 + 232;
                for (let index = indices.length - 1; index > 20; index--) {
                    seed = (seed * 9302 + 49397) % 233280;
                    const swapIndex = Math.floor(seed / 233280 * (index - 20 + 1)) + 20;
                    [indices[index], indices[swapIndex]] = [indices[swapIndex], indices[index]];
                }
                const restored = paragraphs.slice();
                for (let index = 0; index < paragraphs.length; index++) {
                    restored[indices[index]] = paragraphs[index];
                }
                for (let index = 0; index < slots.length; index++) {
                    nodes[slots[index]] = restored[index];
                }
                root.replaceChildren(...nodes);
                document
                    .querySelectorAll('script[src*="chapterlog.js"]')
                    .forEach(node => node.remove());
                root.querySelectorAll('p').forEach(node => node.dataset.bilinovelRestored = 'true');
                return true;
            })()
        """
        return bool(self.tab.run_js(script))

    def _reader_url(self, url: str) -> str:
        """Map a catalog URL to the reader host without changing its path."""
        return re.sub(
            r"^https://(?:www\.)?linovelib\.com",
            self.reader_url_head,
            url,
        )

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
            print("The requested volume number exceeds the number of available volumes.")
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
        text_with_head = bf.find("div", {"id": "TextContent"}) or bf.find(
            "div", {"id": "acontent"}
        )
        if text_with_head is None:
            raise ValueError("Chapter page does not contain a text content container")

        self._remove_non_chapter_content(text_with_head)
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
            text_html = text_html.replace(img_urlre, img_symbol)
            symbol_index = text_html.index(img_symbol)
            if symbol_index > 0 and text_html[symbol_index - 1] != "\n":
                text_html = text_html[:symbol_index] + "\n" + text_html[symbol_index:]

        text_soup = BeautifulSoup(text_html, "html.parser")
        text = text_soup.find("div", id="TextContent") or text_soup.find(
            "div", id="acontent"
        )

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
        notice_index = text.find(msg)
        if notice_index != -1:
            text = text[:notice_index]

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

    @staticmethod
    def _remove_non_chapter_content(content_root) -> None:
        """Remove injected advertising and reader UI without touching prose."""
        for element in content_root.find_all(
            ["script", "style", "iframe", "noscript", "ins"]
        ):
            if element.name in {"iframe", "ins"}:
                container = element.find_parent(["div", "section", "aside"])
                if container is not None and container is not content_root:
                    container.decompose()
                    continue
            element.decompose()

        ad_marker = re.compile(
            r"(?:^|[\s_-])(?:ad|ads|advert(?:isement)?|google-auto-placed|dag)(?:$|[\s_-])",
            re.IGNORECASE,
        )
        for element in content_root.find_all(True):
            marker = " ".join(
                part
                for part in (
                    element.get("id", ""),
                    " ".join(element.get("class", [])),
                )
                if part
            )
            if marker and ad_marker.search(marker):
                element.decompose()

        for element in content_root.find_all(["div", "section", "aside", "center"]):
            if not element.get_text(strip=True) and not element.find("img"):
                element.decompose()

    def get_chap_text(
        self, url: str, chap_name: str, return_next_chapter: bool = False
    ) -> tuple[str, Optional[str]]:
        page_texts: list[str] = []
        page_no = 1
        url = self._reader_url(url)
        url_ori = url
        next_chap_url = None
        while True:
            if page_no == 1:
                str_out = chap_name
            else:
                str_out = f"    Downloading page {page_no}..."
            print(str_out)
            content_html = self.get_html(url, is_gbk=False, is_main_text=True)
            if self._has_content_load_failure(content_html):
                raise IncompleteChapterContentError(
                    "The source returned incomplete chapter content. "
                    f"No reliable ordered fallback is available for {url}."
                )
            text = self.get_page_text(content_html)
            # Continuation pages frequently begin/end with reader-injected
            # <br> elements. Trim only page boundaries, not paragraph breaks.
            text = re.sub(r"^(?:\s|<br\s*/?>)+", "", text)
            text = re.sub(r"(?:\s|<br\s*/?>)+$", "", text)
            if text:
                page_texts.append(text)
            url_new = url_ori.replace(".html", f"_{page_no + 1}.html")[
                len(self.reader_url_head) :
            ]
            if url_new in content_html:
                page_no += 1
                url = self.reader_url_head + url_new
            else:
                if return_next_chapter:
                    next_chap_url = self.url_head + re.search(
                        r'(?:书签|書籤)</a><a href="(.*?)">(?:下一页|下一頁)</a>',
                        content_html,
                    ).group(1)
                break
        return "\n".join(page_texts), next_chap_url

    @staticmethod
    def _has_content_load_failure(content_html: str) -> bool:
        """Return whether Linovelib inserted its incomplete-content marker."""
        return "内容加载失败" in content_html or "內容加載失敗" in content_html

    def get_text(self) -> None:
        self.make_folder()
        text_no = 0
        for chap_no, (chap_name, chap_url) in enumerate(
            zip(self.volume["chap_names"], self.volume["chap_urls"])
        ):
            is_fix_next_chap_url = chap_name in self.missing_last_chap_list
            text, next_chap_url = self.get_chap_text(
                chap_url, chap_name, return_next_chapter=is_fix_next_chap_url
            )
            text = self.convert_text(text)

            # Illustration pages are ordinary catalog chapters.  Keeping them
            # here preserves their source position in both spine and TOC.
            file_name = self.text_path / f"{str(text_no).zfill(2)}.xhtml"
            text_html = text2htmls(chap_name, text)
            text_no += 1
            file_name.write_text(text_html, encoding="utf-8")
            self.chapter_documents.append((chap_name, f"Text/{file_name.name}", True))

            if is_fix_next_chap_url:
                self.volume["chap_urls"][chap_no + 1] = next_chap_url

        # Add the book cover after inline images so no prose illustration is
        # mistaken for a reserved cover slot.  It is metadata, not a chapter.
        if not self.check_url(self.cover_url_back):
            if self.cover_url_back not in self.img_url_map:
                self.img_url_map[self.cover_url_back] = str(len(self.img_url_map)).zfill(2)
            self.cover_image_name = self.img_url_map[self.cover_url_back]

    def get_image(self, is_gui: bool = False, signal=None) -> None:
        for url in self.img_url_map:
            self.pool.submit(self.get_html_content, url)
        img_path = self.img_path
        if is_gui:
            from server.app import session
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
        if self.cover_image_name is None:
            print("No cover image found. Add one manually with a third-party EPUB editor.")
            return
        try:
            imgfile = self.img_path / f"{self.cover_image_name}.jpg"
            img_w, img_h = Image.open(str(imgfile)).size
            signal_msg = (str(imgfile), img_h, img_w)
            if is_gui:
                signal.emit(signal_msg)
        except Exception as e:
            print(e)
            print("No cover image found. Add one manually with a third-party EPUB editor.")

    def check_volume(self, is_gui: bool = False, signal=None, editline=None) -> None:
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

    @staticmethod
    def check_url(url: str) -> bool:
        return "javascript" in url or "cid" in url

    def get_prev_url(self, chap_no: int) -> str:
        content_html = self.get_html(
            self._reader_url(self.volume["chap_urls"][chap_no]),
            is_gbk=False,
            is_main_text=True,
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
            from server.app import session
            content = session.request_input(error_msg)
        else:
            content = input(error_msg)
        return content

    def hand_in_url(
        self, chap_name: str, is_gui: bool = False, signal=None, editline=None
    ) -> str:
        error_msg = (
            f'Chapter "{chap_name}" has an invalid link. Enter its mobile-page URL '
            f'(beginning with "{self.url_head}"): '
        )
        return self.hand_in_msg(error_msg, is_gui, signal, editline)

    def hand_in_color_page_name(
        self, is_gui: bool = False, signal=None, editline=None
    ) -> str:
        if is_gui:
            error_msg = (
                "The illustration page is missing. Select its title, or leave this blank "
                "and confirm to skip it: "
            )
            editline.addItems(self.volume["chap_names"])
            editline.setCurrentIndex(-1)
        else:
            error_msg = (
                "The illustration page is missing. Enter its title, or press Enter to skip it: "
            )
        return self.hand_in_msg(error_msg, is_gui, signal, editline)

    def get_toc(self) -> None:
        # Retained for callers using the historic workflow.  The deterministic
        # packer writes both navigation documents from ``chapter_documents``.
        return None

    def get_content(self) -> None:
        return None

    def get_epub_head(self) -> None:
        return None

    def get_epub(self) -> str:
        import shutil
        import sqlite3
        from datetime import datetime

        # Build book subdirectory: out/book-name/
        safe_book_name = check_chars(self.book_name)
        book_dir = self.epub_path / safe_book_name
        book_dir.mkdir(parents=True, exist_ok=True)

        # Filename: book-name volume-X.epub
        safe_volume_name = check_chars(self.volume['volume_name'])
        epub_name = f"{safe_book_name} {safe_volume_name}"
        epub_file = book_dir / f"{epub_name}.epub"

        # Cache for in-app reader: out/book-name/.library/book-number_volume-number/
        cache_path = book_dir / ".library" / f"{self.book_no}_{self.volume_no}"
        if cache_path.exists():
            shutil.rmtree(cache_path)
        
        packer = EpubPacker(
            f"{self.book_name}-{self.volume['volume_name']}", self.author
        )

        packer.publisher = self.publisher
        packer.description = self.brief
        packer.subjects = self.tag_list
        packer.source = self.main_page
        packer.series = self.book_name
        packer.series_index = self.volume_no
        for title, href, in_toc in self.chapter_documents:
            content = (self.temp_path / "OEBPS" / href).read_text(encoding="utf-8")
            packer.add_chapter(Chapter(title, href, content, in_toc))
        for image in sorted(self.img_path.iterdir(), key=lambda item: item.name):
            if not image.is_file():
                continue
            media_type = PNG if image.suffix.lower() == ".png" else JPEG
            packer.add_resource(Resource(
                f"Images/{image.name}", image.read_bytes(), media_type,
                is_cover=image.name == f"{self.cover_image_name}.jpg",
            ))
        packer.write(epub_file)

        # Keep the in-app reader cache byte-for-byte aligned with the finished
        # EPUB's OEBPS payload rather than an earlier staging directory.
        with zipfile.ZipFile(epub_file) as archive:
            for member in archive.infolist():
                if not member.is_dir() and member.filename.startswith("OEBPS/"):
                    destination = cache_path / member.filename
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.read(member))
                    
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
                str(cache_path / "OEBPS" / "Images" / f"{self.cover_image_name}.jpg")
                if self.cover_image_name is not None else "",
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
                
        return str(epub_file)
