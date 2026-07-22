import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from server.bilinovel.epub_packer import Chapter, EpubPacker, JPEG, Resource


class TestEpubPacker(unittest.TestCase):
    def test_preserves_added_chapter_order_in_spine_and_navigation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "book.epub"
            packer = EpubPacker("Book", "Author")
            packer.add_chapter(Chapter("Second in catalog", "Text/000001.xhtml", "<html/>"))
            packer.add_chapter(Chapter("First in catalog", "Text/000002.xhtml", "<html/>"))
            packer.add_resource(Resource("Images/cover.jpg", b"cover", JPEG, is_cover=True))
            packer.write(output)

            with zipfile.ZipFile(output) as archive:
                infos = archive.infolist()
                self.assertEqual(infos[0].filename, "mimetype")
                self.assertEqual(infos[0].compress_type, zipfile.ZIP_STORED)
                self.assertEqual(archive.read("mimetype"), b"application/epub+zip")
                opf = ET.fromstring(archive.read("OEBPS/content.opf"))
                ncx = ET.fromstring(archive.read("OEBPS/toc.ncx"))

            opf_ns = {"opf": "http://www.idpf.org/2007/opf"}
            ncx_ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
            spine = [node.attrib["idref"] for node in opf.findall("opf:spine/opf:itemref", opf_ns)]
            titles = [node.text for node in ncx.findall("ncx:navMap/ncx:navPoint/ncx:navLabel/ncx:text", ncx_ns)]
            cover = opf.find("opf:manifest/opf:item[@properties='cover-image']", opf_ns)
            self.assertEqual(spine, ["chapter-0", "chapter-1"])
            self.assertEqual(titles, ["Second in catalog", "First in catalog"])
            self.assertEqual(cover.attrib["href"], "Images/cover.jpg")

    def test_rejects_duplicate_document_names(self):
        packer = EpubPacker("Book", "Author")
        packer.add_chapter(Chapter("One", "Text/one.xhtml", "<html/>"))
        with self.assertRaisesRegex(ValueError, "Duplicate chapter href"):
            packer.add_chapter(Chapter("Two", "Text/one.xhtml", "<html/>"))


if __name__ == "__main__":
    unittest.main()
