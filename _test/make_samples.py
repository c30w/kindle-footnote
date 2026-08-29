#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成两个测试用 EPUB：A=标准 EPUB3 aside 脚注；B=脚注单独成文件 + 回跳链接"""
import os, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

CSS = "p{text-indent:2em;line-height:1.7;}\n.footnotes{font-size:0.85em;}\n"


def build_a(path):
    opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Sample A</dc:title><dc:language>zh-CN</dc:language><dc:identifier id="id">a1</dc:identifier>
  </metadata>
  <manifest>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx"><itemref idref="c1"/></spine>
</package>"""

    ch1 = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN" lang="zh-CN">
<head><title>第一章</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body>
  <h1>第一章 测试</h1>
  <p>这是第一段正文，里面有个脚注标记<a href="#fn1" id="ref1" epub:type="noteref">[1]</a>，后面还有内容。</p>
  <p>第二段也有一个<a href="#fn2" id="ref2" epub:type="noteref">[2]</a>，另外还有&nbsp;一个特殊字符 &mdash; 测试。</p>
  <p>第三段没有脚注。</p>
  <p>第四段又引用了第一条<a href="#fn1" id="ref1b" epub:type="noteref">[1]</a>。</p>
  <div class="footnotes">
    <hr/>
    <ol>
      <li id="fn1" epub:type="footnote"><p><a href="#ref1">&#8617;</a>这是第一条脚注的内容，比较长一点，用来观察内嵌效果。</p></li>
      <li id="fn2" epub:type="footnote"><p><a href="#ref2">&#8617;</a>这是第二条脚注。<br/>它有两个段落。</p><p>第二段内容。</p></li>
    </ol>
  </div>
</body>
</html>"""

    ncx = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="a1"/></head>
  <docTitle><text>Sample A</text></docTitle>
  <navMap><navPoint id="n1" playOrder="1"><navLabel><text>第一章</text></navLabel><content src="ch1.xhtml"/></navPoint></navMap>
</ncx>"""

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/style.css", CSS)
        z.writestr("OEBPS/ch1.xhtml", ch1)
        z.writestr("OEBPS/toc.ncx", ncx)
    print("built", path)


def build_b(path):
    """脚注集中在独立文件 notes.xhtml，靠回跳链接定位（中文书常见）"""
    opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Sample B</dc:title><dc:language>zh-CN</dc:language><dc:identifier id="id">b1</dc:identifier>
  </metadata>
  <manifest>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="nt" href="notes.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/><itemref idref="nt"/></spine>
</package>"""

    ch1 = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN" lang="zh-CN">
<head><title>正文</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body>
  <h1>第一章</h1>
  <p>正文里出现注释<a href="notes.xhtml#n1" id="m1" epub:type="noteref">〔1〕</a>，继续往下读。</p>
  <ul><li>列表项里也有注释<a href="notes.xhtml#n2" id="m2" epub:type="noteref">〔2〕</a></li></ul>
  <table><tr><td>表格里的注释<a href="notes.xhtml#n3" id="m3" epub:type="noteref">〔3〕</a></td></tr></table>
</body>
</html>"""

    notes = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN" lang="zh-CN">
<head><title>注释</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body>
  <h2>注释</h2>
  <div class="notes-list">
    <aside id="n1" epub:type="footnote"><a href="ch1.xhtml#m1">&#8617;</a>第一条注释文字。</aside>
    <aside id="n2" epub:type="footnote"><a href="ch1.xhtml#m2">&#8617;</a>第二条注释文字。</aside>
    <aside id="n3" epub:type="footnote"><a href="ch1.xhtml#m3">&#8617;</a>第三条注释文字。</aside>
  </div>
</body>
</html>"""

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/style.css", CSS)
        z.writestr("OEBPS/ch1.xhtml", ch1)
        z.writestr("OEBPS/notes.xhtml", notes)
    print("built", path)


if __name__ == "__main__":
    build_a(os.path.join(HERE, "sample_a.epub"))
    build_b(os.path.join(HERE, "sample_b.epub"))
