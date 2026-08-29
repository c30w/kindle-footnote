#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成"脏"样本 C：不规范 HTML + 只有 class 的脚注 + epub:type 套在容器上"""
import os, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>Sample C</dc:title><dc:language>zh-CN</dc:language><dc:identifier id="id">c1</dc:identifier>
  </metadata>
  <manifest>
    <item id="c1" href="part1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/></spine>
</package>"""

# 故意不规范：未闭合的 <br>、裸 &nbsp;、大小写混用
PART1 = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">
<head><title>卷一</title></head>
<body>
<P>第一段，带注释<a href="#f1" class="noteref">①</a>。<br>
换行之后继续。</P>
<p>第二段引用第二条<a href="#f2" class="noteref">②</a>&nbsp;结束。</p>
<div class="footnotes" epub:type="footnote" xmlns:epub="http://www.idpf.org/2007/ops">
  <div class="footnote" id="f1"><a href="#f1" class="backlink">↩</a>【一】第一条注释。</div>
  <div class="footnote" id="f2"><a href="#f2" class="backlink">↩</a>【二】第二条注释。</div>
</div>
</body>
</html>"""


def build(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/content.opf", OPF)
        z.writestr("OEBPS/part1.xhtml", PART1)
    print("built", path)


if __name__ == "__main__":
    build(os.path.join(HERE, "sample_c.epub"))
