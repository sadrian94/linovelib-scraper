"""Shared utilities for bilimanga backend."""

from __future__ import annotations

from PIL import Image
import pillow_avif  # noqa: F401


def get_cover_html(img_w: int, img_h: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>Cover</title>
</head>
<body>
  <div style="text-align: center; padding: 0pt; margin: 0pt;">
    <svg xmlns="http://www.w3.org/2000/svg" height="100%" preserveAspectRatio="xMidYMid meet" version="1.1" viewBox="0 0 {img_w} {img_h}" width="100%" xmlns:xlink="http://www.w3.org/1999/xlink">
      <image width="{img_w}" height="{img_h}" xlink:href="../Images/cover.jpg"/>
    </svg>
  </div>
</body>
</html>"""


def get_xhtml(img_name: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title></title>
</head>
<body>
  <img alt="{img_name}" src="../Images/{img_name}"/>
</body>
</html>"""


def get_toc_html(title: str, chap_names: list[str], chap_imgs: list[str]) -> str:
    toc_html_template = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"
   "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:depth" content="0" />
    <meta name="dtb:totalPageCount" content="0" />
    <meta name="dtb:maxPageNumber" content="0" />
  </head>
  <docTitle>
    <text>{title}</text>
  </docTitle>
  <navMap>
{nav_points}
  </navMap>
</ncx>
"""
    nav_point_template = """   <navPoint id="navPoint-{chap_no}" playOrder="{chap_no}">
      <navLabel>
        <text>{chap_name}</text>
      </navLabel>
      <content src="Text/{chap_img_xhtml}"/>
    </navPoint>
"""
    nav_points = "\n".join(
        nav_point_template.format(
            chap_no=i + 1,
            chap_name=chap_name,
            chap_img_xhtml=chap_img.replace(".jpg", ".xhtml"),
        )
        for i, (chap_name, chap_img) in enumerate(zip(chap_names, chap_imgs))
    )
    return toc_html_template.format(title=title, nav_points=nav_points)


def get_content_html(
    book_name: str,
    volume_name: str,
    volume_no: int,
    author: str,
    brief: str,
    tag_list: list[str],
    img_list: list[str],
) -> str:
    content_htmls = """<?xml version="1.0" encoding="utf-8"?>
<package version="2.0" unique-identifier="BookId" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:language>zh-TW</dc:language>
    <meta name="calibre:series" content="{series_name}" />
    <meta name="calibre:series_index" content="{series_no}"/>
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:description>{brief}</dc:description>
{subjects}
    <meta name="cover" content="cover.jpg"/>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
{item1}
    <item id="cover.xhtml" href="Text/cover.xhtml" media-type="application/xhtml+xml"/>
{item2}
    <item id="cover.jpg" href="Images/cover.jpg" media-type="image/jpeg"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="cover.xhtml"/>
{item3}
  </spine>
  <guide>
    <reference type="cover" title="封面" href="Text/cover.xhtml"/>
  </guide>
</package>
"""

    subjects = "\n".join(f"    <dc:subject>{tag}</dc:subject>\n" for tag in tag_list)
    item1 = "\n".join(
        f'    <item id="x{img.replace(".jpg", ".xhtml")}" href="Text/{img.replace(".jpg", ".xhtml")}" media-type="application/xhtml+xml"/>'
        for img in img_list
    )
    item2 = "\n".join(
        f'    <item id="x{img}" href="Images/{img}" media-type="image/jpeg"/>'
        for img in img_list
    )
    item3 = "\n".join(
        f'    <itemref idref="x{img.replace(".jpg", ".xhtml")}"/>' for img in img_list
    )

    return content_htmls.format(
        series_name=book_name,
        series_no=volume_no,
        title=f"{book_name}-{volume_name}",
        author=author,
        brief=brief,
        subjects=subjects,
        item1=item1,
        item2=item2,
        item3=item3,
    )


def get_container_html() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>
"""


WIN_ILLEGAL_CHARS = '?*"<>|:/\\'


def check_chars(win_chars: str) -> str:
    return "".join(
        "\u25A0" if char in WIN_ILLEGAL_CHARS else char for char in win_chars
    )


def convert_avif_to_jpg(input_path: str, output_path: str) -> None:
    try:
        with Image.open(input_path) as img:
            img = img.convert("RGB")
            img.save(output_path, "JPEG")
    except Exception as e:
        print(f"Failed to convert {input_path} to {output_path}: {e}")
