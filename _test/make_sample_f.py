#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 sample_f.epub：模拟《红楼梦》校注本那种「驼峰类名 + 互相回跳」的书。

真实结构长这样，全书没有任何 epub:type 语义标记：

  正文角标：<span class="subScript"><a id="jzyy_1_23" href="part0002.html#jz_1_23">(1)</a></span>
  注释定义：<p class="noteContent"><a id="jz_1_23" href="part0002.html#jzyy_1_23">(1)</a> 注释正文</p>

两个关键坑：
  1. 类名是驼峰的 noteContent，脚注里那个 note 后面紧跟大写 C，
     按「独立单词」判断会漏掉 —— 必须能拆驼峰。
  2. 角标外层还有个 subScript 的 span，里面带 sub 字样，
     不能因为它长得像"下标"就被误判成注释定义，否则正文会被整段搬走。

期望的转换结果：3 条注释全部命中，每个角标后面跟的注释编号一致。
"""
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sample_f.epub")

# (注释编号, 定义 id, 角标 id)
PAIRS = [
    ("1", "jz_1_23", "jzyy_1_23"),
    ("2", "jz_2_23", "jzyy_2_23"),
    ("3", "jz_3_23", "jzyy_3_23"),
]

BODY = [
    "第一段正文，引了注释一{0}，后面还有点别的字。",
    "第二段正文，引了注释二{0}。这里一段里引了两条注，用来验证同段多注的排布。",
    "第三段正文，引了注释三{0}。",
]

NOTES = [
    "通灵──“通灵宝玉”的简称。",
    "《石头记》──此书的本名。",
    "饫甘餍肥──意谓饱食美味佳肴。",
]

DOC = "part0002.html"


def build_content():
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<!DOCTYPE html>',
             '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">',
             "<head><title>驼峰类名的书</title>",
             '<meta charset="utf-8"/>',
             '<link rel="stylesheet" type="text/css" href="../stylesheet.css"/>',
             "</head><body>"]

    # 第二段故意引两条注释，验证同一段跟多条注时的顺序
    markers_by_para = [["1"], ["2", "3"], []]
    for i, tpl in enumerate(BODY):
        spans = []
        for num in markers_by_para[i]:
            _, def_id, ref_id = PAIRS[int(num) - 1]
            spans.append('<span class="subScript"><a id="%s" href="%s#%s" '
                         'class="calibre1">(%s)</a></span>'
                         % (ref_id, DOC, def_id, num))
        parts.append('<p class="bodyContent">%s</p>' % tpl.format("".join(spans)))

    parts.append('<p class="calibre3">--------------------</p>')
    for (num, def_id, ref_id), text in zip(PAIRS, NOTES):
        parts.append('<p class="noteContent"><a id="%s" href="%s#%s" '
                     'class="calibre1">(%s)</a> %s</p>'
                     % (def_id, DOC, ref_id, num, text))

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
    <dc:title>驼峰类名的书</dc:title>
    <dc:language>zh-CN</dc:language>
    <dc:identifier id="BookId">sample-f-0001</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="ch1" href="xhtml/%s" media-type="application/xhtml+xml"/>
    <item id="css" href="stylesheet.css" media-type="text/css"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="ch1"/>
  </spine>
</package>
""" % DOC

NCX = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="sample-f-0001"/></head>
  <docTitle><text>驼峰类名的书</text></docTitle>
  <navMap>
    <navPoint id="np1" playOrder="1">
      <navLabel><text>第一章</text></navLabel>
      <content src="xhtml/%s"/>
    </navPoint>
  </navMap>
</ncx>
""" % DOC

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
        z.writestr("OEBPS/xhtml/" + DOC, build_content(), zipfile.ZIP_DEFLATED)
    print("已生成 %s" % OUT)


if __name__ == "__main__":
    main()
