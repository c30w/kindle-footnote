#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 sample_e.epub：模拟「多看/微信读书导出」那种链接错位的书。

这正是老陈那本《九诗心》的真实情况：
  - 注释条目有的没写 id，回跳链接是死的 href="#"
  - 正文角标的 href 指到了别的注释上（角标 [2] 指向内容其实是 [4] 的那条）
  - 有的注释被两个角标同时指向（[5] 和 [6] 都链到 [5]）

期望的转换结果：每个角标 [k] 后面跟的那条注释，编号必须也是 k。
"""
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sample_e.epub")

# (角标编号, 角标 href 指向的注释 id)  —— href 故意指错
MARKERS = [
    ("1", "footnote-5-11"),   # 正确
    ("2", "footnote-5-44"),   # 错位：指到 [4] 那条
    ("3", "footnote-5-33"),   # 正确
    ("4", "footnote-5-44"),   # 正确
    ("5", "footnote-5-55"),   # 正确
    ("6", "footnote-5-55"),   # 重复：也指到 [5] 那条
]

# (注释编号, 是否有 id, 回跳 href)
NOTES = [
    ("1", "footnote-5-11", "noteref-5-11"),
    ("2", "footnote-5-22", "noteref-5-22"),   # 有 id，但没人链过来
    ("3", None,             "#"),             # 没 id，死回跳
    ("4", "footnote-5-44", "noteref-5-44"),
    ("5", "footnote-5-55", "noteref-5-55"),
    ("6", None,             "#"),             # 没 id，死回跳
]

BODY = [
    "第一段正文，引了注释一{0}。后面还有点别的字。",
    "第二段正文，引了注释二{0}。这里故意把链接指错。",
    "第三段正文，引了注释三{0}。",
    "第四段正文，引了注释四{0}。",
    "第五段正文，引了注释五{0}。",
    "第六段正文，引了注释六{0}。",
]


def build_content():
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<!DOCTYPE html>',
             '<html xmlns="http://www.w3.org/1999/xhtml" '
             'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">',
             "<head><title>链接错位的书</title>",
             '<meta charset="utf-8"/>',
             '<link rel="stylesheet" type="text/css" href="../stylesheet.css"/>',
             "</head><body>"]

    for i, tpl in enumerate(BODY):
        num, href = MARKERS[i]
        marker = ('<sup class="calibre18"><a epub:type="noteref" '
                  'href="#%s" id="noteref-5-%s">[%s]</a></sup>' % (href, num, num))
        parts.append('<p class="calibre7"><span class="calibre10">%s</span></p>'
                     % tpl.format(marker))

    for num, nid, back in NOTES:
        id_attr = ' id="%s"' % nid if nid else ""
        parts.append(
            '<p><aside epub:type="footnote"%s><ol class="duokan-footnote-content">'
            '<li class="duokan-footnote-item"><a href="#%s">[%s]</a>'
            '这是第 %s 条注释的正文，编号写在最前面。</li></ol></aside></p>'
            % (id_attr, back, num, num))

    parts.append("</body></html>")
    return "\n".join(parts)


CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>链接错位的书</dc:title>
    <dc:language>zh-CN</dc:language>
    <dc:identifier id="BookId">sample-e-0001</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="ch1" href="xhtml/chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="stylesheet.css" media-type="text/css"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="ch1"/>
  </spine>
</package>
"""

NCX = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="sample-e-0001"/></head>
  <docTitle><text>链接错位的书</text></docTitle>
  <navMap>
    <navPoint id="np1" playOrder="1">
      <navLabel><text>第一章</text></navLabel>
      <content src="xhtml/chapter1.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
"""

CSS = "body{margin:0;padding:0;}\n"


def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, "w") as z:
        # mimetype 必须是第一个且未压缩
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONTAINER, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", OPF, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", NCX, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/stylesheet.css", CSS, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/xhtml/chapter1.xhtml", build_content(), zipfile.ZIP_DEFLATED)
    print("已生成 %s" % OUT)


if __name__ == "__main__":
    main()
