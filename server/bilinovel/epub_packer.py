"""Deterministic EPUB 3 writer.

The downloader deliberately keeps source order separate from download order.  This
module is the only place that turns those ordered resources into an EPUB archive.
It follows the structure used by ``bili_novel_packer``: each chapter is added to
the manifest, spine, NCX and XHTML navigation documents at the same time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import zipfile
from xml.etree import ElementTree as ET


XHTML = "application/xhtml+xml"
JPEG = "image/jpeg"
PNG = "image/png"
NCX = "application/x-dtbncx+xml"


@dataclass(frozen=True)
class Chapter:
    """A spine document, retained in its catalog position."""

    title: str
    href: str
    content: str
    in_toc: bool = True


@dataclass(frozen=True)
class Resource:
    href: str
    content: bytes
    media_type: str
    is_cover: bool = False


class EpubPacker:
    """Build a standards-oriented EPUB without relying on filesystem ordering."""

    def __init__(self, title: str, creator: str, *, language: str = "zh-CN") -> None:
        self.title = title
        self.creator = creator
        self.language = language
        self.publisher = ""
        self.description = ""
        self.subjects: list[str] = []
        self.source = ""
        self.series = ""
        self.series_index: int | None = None
        self._chapters: list[Chapter] = []
        self._resources: list[Resource] = []

    def add_chapter(self, chapter: Chapter) -> None:
        if any(item.href == chapter.href for item in self._chapters):
            raise ValueError(f"Duplicate chapter href: {chapter.href}")
        self._chapters.append(chapter)

    def add_resource(self, resource: Resource) -> None:
        if any(item.href == resource.href for item in self._resources):
            raise ValueError(f"Duplicate resource href: {resource.href}")
        self._resources.append(resource)

    def write(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        identifier = f"urn:uuid:{uuid4()}"
        entries = self._entries(identifier)
        # EPUB requires mimetype to be first and stored rather than compressed.
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(
                zipfile.ZipInfo("mimetype"), "application/epub+zip",
                compress_type=zipfile.ZIP_STORED,
            )
            for name, data in entries:
                archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

    def _entries(self, identifier: str) -> list[tuple[str, bytes | str]]:
        entries: list[tuple[str, bytes | str]] = [
            ("META-INF/container.xml", self._container()),
        ]
        entries.extend((f"OEBPS/{chapter.href}", chapter.content) for chapter in self._chapters)
        entries.extend((f"OEBPS/{resource.href}", resource.content) for resource in self._resources)
        entries.extend([
            ("OEBPS/toc.ncx", self._ncx(identifier)),
            ("OEBPS/toc.xhtml", self._nav()),
            ("OEBPS/content.opf", self._opf(identifier)),
        ])
        return entries

    @staticmethod
    def _xml(element: ET.Element) -> str:
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
            element, encoding="unicode", short_empty_elements=True
        )

    def _container(self) -> str:
        root = ET.Element("container", {"version": "1.0", "xmlns": "urn:oasis:names:tc:opendocument:xmlns:container"})
        rootfiles = ET.SubElement(root, "rootfiles")
        ET.SubElement(rootfiles, "rootfile", {"full-path": "OEBPS/content.opf", "media-type": "application/oebps-package+xml"})
        return self._xml(root)

    def _ncx(self, identifier: str) -> str:
        root = ET.Element("ncx", {"xmlns": "http://www.daisy.org/z3986/2005/ncx/", "version": "2005-1"})
        head = ET.SubElement(root, "head")
        for name, content in (("dtb:uid", identifier), ("dtb:depth", "1"), ("dtb:totalPageCount", "0"), ("dtb:maxPageNumber", "0")):
            ET.SubElement(head, "meta", {"name": name, "content": content})
        doc_title = ET.SubElement(root, "docTitle")
        ET.SubElement(doc_title, "text").text = self.title
        nav_map = ET.SubElement(root, "navMap")
        for index, chapter in enumerate((c for c in self._chapters if c.in_toc), 1):
            point = ET.SubElement(nav_map, "navPoint", {"id": f"navPoint-{index}", "playOrder": str(index)})
            label = ET.SubElement(point, "navLabel")
            ET.SubElement(label, "text").text = chapter.title
            ET.SubElement(point, "content", {"src": chapter.href})
        return self._xml(root)

    def _nav(self) -> str:
        root = ET.Element("html", {"xmlns": "http://www.w3.org/1999/xhtml", "xmlns:epub": "http://www.idpf.org/2007/ops", "xml:lang": self.language})
        head = ET.SubElement(root, "head")
        ET.SubElement(head, "meta", {"charset": "UTF-8"})
        ET.SubElement(head, "title").text = "目录"
        body = ET.SubElement(root, "body")
        nav = ET.SubElement(body, "nav", {"epub:type": "toc", "id": "toc"})
        ET.SubElement(nav, "h1").text = "目录"
        listing = ET.SubElement(nav, "ol")
        for chapter in (c for c in self._chapters if c.in_toc):
            item = ET.SubElement(listing, "li")
            ET.SubElement(item, "a", {"href": chapter.href}).text = chapter.title
        return self._xml(root)

    def _opf(self, identifier: str) -> str:
        root = ET.Element("package", {"xmlns": "http://www.idpf.org/2007/opf", "version": "3.0", "unique-identifier": "book-id"})
        metadata = ET.SubElement(root, "metadata", {"xmlns:dc": "http://purl.org/dc/elements/1.1/"})
        ET.SubElement(metadata, "dc:identifier", {"id": "book-id"}).text = identifier
        ET.SubElement(metadata, "dc:title").text = self.title
        ET.SubElement(metadata, "dc:creator").text = self.creator
        ET.SubElement(metadata, "dc:language").text = self.language
        for tag, value in (("dc:publisher", self.publisher), ("dc:description", self.description), ("dc:source", self.source)):
            if value:
                ET.SubElement(metadata, tag).text = value
        for subject in self.subjects:
            ET.SubElement(metadata, "dc:subject").text = subject
        ET.SubElement(metadata, "meta", {"property": "dcterms:modified"}).text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if self.series:
            ET.SubElement(metadata, "meta", {"name": "calibre:series", "content": self.series})
        if self.series_index is not None:
            ET.SubElement(metadata, "meta", {"name": "calibre:series_index", "content": str(self.series_index)})
        manifest = ET.SubElement(root, "manifest")
        ET.SubElement(manifest, "item", {"id": "ncx", "href": "toc.ncx", "media-type": NCX})
        ET.SubElement(manifest, "item", {"id": "nav", "href": "toc.xhtml", "media-type": XHTML, "properties": "nav"})
        for index, chapter in enumerate(self._chapters):
            ET.SubElement(manifest, "item", {"id": f"chapter-{index}", "href": chapter.href, "media-type": XHTML})
        for index, resource in enumerate(self._resources):
            attributes = {"id": f"resource-{index}", "href": resource.href, "media-type": resource.media_type}
            if resource.is_cover:
                attributes["properties"] = "cover-image"
            ET.SubElement(manifest, "item", attributes)
        spine = ET.SubElement(root, "spine", {"toc": "ncx"})
        for index, _ in enumerate(self._chapters):
            ET.SubElement(spine, "itemref", {"idref": f"chapter-{index}"})
        return self._xml(root)
