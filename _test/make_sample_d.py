#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""样本 D：同一段引用两条注（测 adjacent 紧凑）+ 注释正文自带编号（测不重复加标号）"""
import os, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Sample D</dc:title><dc:language>zh-CN</dc:language><dc:identifier id="id">d1</dc:identifier>
  </metadata>
  <manifest><item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="c1"/></spine>
</package>"""

CH1 = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">
<head><title>第一章</title></head>
<body>
  <h1>第一章</h1>
  <p>同一段里连着引两条<a href="#n1" id="r1" epub:type="noteref">[1]</a><a href="#n2" id="r2" epub:type="noteref">[2]</a>，应该紧挨着排。</p>
  <p>这条注释自带编号<a href="#n3" id="r3" epub:type="noteref">[3]</a>。</p>
  <p>这条注释没有编号<a href="#n4" id="r4" epub:type="noteref">[4]</a>。</p>
  <p>这条注释以年份开头<a href="#n5" id="r5" epub:type="noteref">[5]</a>。</p>

  <div class="footnotes">
    <aside id="n1" epub:type="footnote"><a href="#r1">&#8617;</a>第一条：正文没有编号，应该补上 [1]。</aside>
    <aside id="n2" epub:type="footnote"><a href="#r2">&#8617;</a>第二条：正文没有编号，应该补上 [2]，且紧贴第一条。</aside>
    <aside id="n3" epub:type="footnote"><a href="#r3">&#8617;</a>【3】正文已经带了编号，不该再补一个。</aside>
    <aside id="n4" epub:type="footnote"><a href="#r4">&#8617;</a>第四条：没有编号，需要补上。</aside>
    <aside id="n5" epub:type="footnote"><a href="#r5">&#8617;</a>1848 年发生了很多事，年份不该被当成编号。</aside>
  </div>
</body>
</html>"""


def build(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/content.opf", OPF)
        z.writestr("OEBPS/ch1.xhtml", CH1)
    print("built", path)


if __name__ == "__main__":
    build(os.path.join(HERE, "sample_d.epub"))
