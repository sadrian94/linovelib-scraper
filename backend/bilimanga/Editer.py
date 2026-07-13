"""Manga EPUB packager."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from .utils import (
    check_chars,
    get_container_html,
    get_content_html,
    get_cover_html,
    get_toc_html,
    get_xhtml,
)


class Editer:
    def __init__(
        self,
        book_name: str,
        volume_name: str,
        volume_no: int,
        author: str,
        brief: str,
        tag_list: list[str],
        chap_list: list[str],
        comic_root: Path | str,
        out_root: str,
        delete_comic: bool = False,
    ):
        self.book_name = book_name
        self.author = author
        self.chap_list = chap_list
        self.comic_root = Path(comic_root)
        self.volume_name = volume_name
        self.volume_no = volume_no
        self.temp_path_io = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_path_io.name)
        self.out_root = Path(out_root)
        self.brief = brief
        self.tag_list = tag_list
        self.delete_comic = delete_comic

        self.img_list: list[str] = []
        self.chap_first_imgs: list[str] = []

    def pack_img(self) -> None:
        self.epub_path = self.temp_path / "tmp"
        self.epub_oebps_path = self.epub_path / "OEBPS"
        self.epub_img_path = self.epub_oebps_path / "Images"
        self.epub_text_path = self.epub_oebps_path / "Text"
        self.epub_img_path.mkdir(parents=True, exist_ok=True)
        self.epub_text_path.mkdir(parents=True, exist_ok=True)

        print("正在打包处理图片......")
        for chap_no, chap in enumerate(self.chap_list):
            img_path = self.comic_root / check_chars(chap)
            imgs = sorted(img_path.iterdir()) if img_path.exists() else []
            img_no = 0
            self.chap_first_imgs.append(
                f"{str(chap_no).zfill(3)}_{str(0).zfill(4)}.jpg"
            )
            for img_no, img in enumerate(imgs):
                img_new = (
                    f"{str(chap_no).zfill(3)}_{str(img_no).zfill(4)}.jpg"
                )
                img_epub_path = self.epub_img_path / img_new
                shutil.copyfile(str(img), str(img_epub_path))
                self.img_list.append(img_new)

    def typesetting(self) -> None:
        print("正在生成排版......")
        for img in self.img_list:
            text_file = self.epub_text_path / img.replace(".jpg", ".xhtml")
            text_file.write_text(get_xhtml(img), encoding="utf-8")

        print("正在生成元数据......")

        # Cover
        cover_path = self.epub_img_path / "cover.jpg"
        shutil.copyfile(
            str(self.comic_root / "cover.jpg"), str(cover_path)
        )
        cover_text = self.epub_text_path / "cover.xhtml"
        img = Image.open(str(cover_path))
        img_array = np.array(img)
        cover_text.write_text(
            get_cover_html(img_array.shape[1], img_array.shape[0]),
            encoding="utf-8",
        )

        # Content OPF
        content_htmls = get_content_html(
            self.book_name,
            self.volume_name,
            self.volume_no,
            self.author,
            self.brief,
            self.tag_list,
            self.img_list,
        )
        (self.epub_oebps_path / "content.opf").write_text(
            content_htmls, encoding="utf-8"
        )

        # TOC
        toc_htmls = get_toc_html(
            self.book_name, self.chap_list, self.chap_first_imgs
        )
        (self.epub_oebps_path / "toc.ncx").write_text(
            toc_htmls, encoding="utf-8"
        )

        # EPUB header
        (self.epub_path / "mimetype").write_text("application/epub+zip")
        metainf = self.epub_path / "META-INF"
        metainf.mkdir(exist_ok=True)
        (metainf / "container.xml").write_text(
            get_container_html(), encoding="utf-8"
        )

    def get_epub(self) -> None:
        print("正在打包EPUB......")
        epub_name = check_chars(f"{self.book_name}-{self.volume_name}")
        epub_file = self.out_root / f"{epub_name}.epub"
        with zipfile.ZipFile(str(epub_file), "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath_str, _, filenames in self.epub_path.walk():
                fpath = dirpath_str.relative_to(self.epub_path)
                fpath_str = str(fpath) if str(fpath) != "." else ""
                for filename in filenames:
                    zf.write(
                        str(dirpath_str / filename),
                        f"{fpath_str}/{filename}" if fpath_str else filename,
                    )
        self.temp_path_io.cleanup()
        if self.delete_comic:
            shutil.rmtree(self.comic_root)
        print(f"EPUB生成成功, 路径【{epub_file}】")

    def get_cover(self, is_gui: bool = False, signal=None) -> None:
        imgfile = self.comic_root / "cover.jpg"
        try:
            img = Image.open(str(imgfile))
            img_w, img_h = img.size
            signal_msg = (str(imgfile), img_h, img_w)
            if is_gui:
                signal.emit(signal_msg)
        except Exception as e:
            print(e)
            print("没有封面图片，请自行用第三方EPUB编辑器手动添加封面")
