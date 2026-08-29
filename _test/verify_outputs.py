#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验转换产物是否是一本合法 EPUB，并检查本次改动的几个关键点。"""
import glob
import os
import re
import sys
import zipfile

from lxml import etree

FAIL = []


def check(name, ok, detail=""):
    if not ok:
        FAIL.append("%s: %s" % (name, detail))
    print("  %s %s%s" % ("OK " if ok else "FAIL", name, ("  -> " + detail) if detail and not ok else ""))


def verify(path):
    print("=" * 60)
    print(os.path.basename(path))
    z = zipfile.ZipFile(path)

    # 1. mimetype 必须是第一个 entry 且未压缩
    names = z.namelist()
    check("mimetype 是第一个文件", names[0] == "mimetype", names[0])
    info = z.getinfo("mimetype")
    check("mimetype 未压缩(STORED)", info.compress_type == zipfile.ZIP_STORED, str(info.compress_type))
    check("mimetype 内容正确", z.read("mimetype") == b"application/epub+zip")

    # 2. zip 完整性
    check("zip 无损坏", z.testzip() is None, str(z.testzip()))

    # 3. 所有 xml/opf/xhtml 都能解析
    bad = []
    for n in names:
        if n.endswith((".xhtml", ".html", ".opf", ".xml")):
            try:
                etree.fromstring(z.read(n))
            except Exception as e:
                bad.append("%s (%s)" % (n, e))
    check("所有 XML 可解析", not bad, "; ".join(bad))

    # 4. OPF：manifest 里引用的文件必须都在 zip 里；spine 里不能有已删除的
    opf_name = None
    for n in names:
        if n.endswith(".opf"):
            opf_name = n
            break
    if opf_name:
        root = etree.fromstring(z.read(opf_name))
        ns = {"o": "http://www.idpf.org/2007/opf"}
        base = posix_dir(opf_name)
        missing = []
        for item in root.iter("{%s}item" % ns["o"]):
            href = item.get("href")
            if not href or href.startswith(("http", "mailto")):
                continue
            full = posix_norm(base, href)
            if full not in names:
                missing.append(full)
        check("manifest 引用的文件都在包内", not missing, "; ".join(missing))

        spine_ids = [s.get("idref") for s in root.iter("{%s}itemref" % ns["o"])]
        check("spine 非空", bool(spine_ids))
    else:
        check("存在 OPF", False)

    # 5. 本次改动：内嵌注释块、样式、标号
    body_html = b""
    for n in names:
        if n.endswith((".xhtml", ".html")):
            body_html += z.read(n)

    n_notes = len(re.findall(rb'class="[^"]*kfx-inline-note', body_html))
    check("存在内嵌注释块", n_notes > 0, str(n_notes))

    has_css = b"kfx-inline-note{" in body_html
    check("已注入 CSS", has_css)

    # 行距应为 1 倍（tight / compact 两档）
    if "loose" not in os.path.basename(path):
        m = re.search(rb"\.kfx-inline-note\{([^}]*)\}", body_html)
        if m:
            decl = m.group(1).decode("utf-8", "ignore")
            lh = re.search(r"line-height:\s*([0-9.]+)", decl)
            check("注释块 line-height=1", bool(lh) and lh.group(1) == "1", decl[:80])

    # 顺序：kfxnote-N 的 id 必须递增出现
    ids = [int(x) for x in re.findall(rb'id="kfxnote-(\d+)"', body_html)]
    check("注释 id 顺序递增", ids == sorted(ids), str(ids))

    # 不应残留 epub:type="footnote" 的 aside
    left = len(re.findall(rb'epub:type="[^"]*footnote', body_html))
    check("无残留 footnote 语义标记", left == 0, "%d 处" % left)

    # 标号：每条注释块开头应有编号（除非 --no-label 或自带编号）
    labels = re.findall(rb'<span class="kfx-note-label">([^<]*)</span>', body_html)
    print("     注释块 %d 个，其中 %d 个带自动编号" % (n_notes, len(labels)))


def posix_dir(p):
    return posixpath_dir(p)


def posixpath_dir(p):
    return os.path.dirname(p).replace("\\", "/")


def posix_norm(base, href):
    if base:
        return (base + "/" + href).replace("\\", "/")
    return href.replace("\\", "/")


if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out_*.epub")))
    if not files:
        sys.exit("没有找到 out_*.epub，先跑一遍转换")
    for f in files:
        verify(f)
    print("=" * 60)
    if FAIL:
        print("失败 %d 项：" % len(FAIL))
        for x in FAIL:
            print("  - " + x)
        sys.exit(1)
    print("全部通过")
