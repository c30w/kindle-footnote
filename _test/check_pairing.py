#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查转换结果里「角标编号」和「它后面那条注释的编号」是否对得上。

这是最关键的正确性指标：链接错位的书（sample_e / 老陈的真书）如果按 href 走，
角标 [2] 后面会插成注释 [4] 的内容 —— 比不处理还糟。
"""
import glob
import os
import re
import sys

import zipfile

def note_number_of(s):
    """只认开头那个编号（和主程序保持同一套判断）"""
    LEAD = re.compile(r"^[\s　\[\]【】〔〕()（）<>《》「」『』⟦⟧\{\}\.、:：,，;；]{0,6}")
    NUM = re.compile(r"(\d+|[一二三四五六七八九十百千万零〇两]+|"
                     r"[\u2460-\u2473\u3251-\u325f\u32b1-\u32bf]+)")
    if not s:
        return None
    m = NUM.match(s[LEAD.match(s).end():])
    if not m:
        return None
    tok = m.group(1)
    if tok.isascii() and tok.isdecimal():
        return str(int(tok))
    cp = ord(tok[0])
    if 0x2460 <= cp <= 0x2473:
        return str(cp - 0x2460 + 1)
    if 0x3251 <= cp <= 0x325F:
        return str(cp - 0x3251 + 1)
    if 0x32B1 <= cp <= 0x32BF:
        return str(cp - 0x32B1 + 1)
    CN = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
          "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    U = {"十": 10, "百": 100, "千": 1000}
    sec = num = 0
    found = False
    for ch in tok:
        if ch in CN:
            found = True
            num = CN[ch]
        elif ch in U:
            found = True
            sec += (num or 1) * U[ch]
            num = 0
        else:
            break
    return str(sec + num) if found else None


def strip_tags(html):
    return re.sub(r"<[^>]+>", "", html)


def check(path):
    z = zipfile.ZipFile(path)
    ok = bad = skipped = 0
    bad_samples = []
    for n in z.namelist():
        if not n.endswith((".xhtml", ".html")):
            continue
        s = z.read(n).decode("utf-8", "ignore")
        # 按顺序扫：遇到角标记下编号，遇到注释块就和下一個待匹配的角标比对
        # 同一段里可能连着好几个角标，注释块会依次排在段后，所以用队列而不是单个变量
        pending = []
        for m in re.finditer(
                # 注释块可能是 div / p / li / aside —— 取决于原书注释条目用的什么标签，
                # 只认 div 会整条漏掉，队列一错位后面全是假错配
                r'<sup class="kfx-note-marker">(.*?)</sup>'
                r'|<(?:div|p|li|aside|section|blockquote)\b[^>]*class="[^"]*kfx-inline-note[^"]*"[^>]*>',
                s, re.S):
            frag = m.group(0)
            if "kfx-note-marker" in frag:
                txt = strip_tags(m.group(1)).strip()
                num = note_number_of(txt)
                if num is not None:
                    pending.append(num)
            else:
                if not pending:
                    continue
                want = pending.pop(0)
                # 取注释块开头 20 字判断编号
                tail = strip_tags(s[m.end():m.end() + 120]).strip()
                nnum = note_number_of(tail[:20])
                if nnum is None:
                    skipped += 1
                elif nnum == want:
                    ok += 1
                else:
                    bad += 1
                    if len(bad_samples) < 6:
                        bad_samples.append("%s 角标[%s] 后面是注释[%s]：%s"
                                           % (n.rsplit("/", 1)[-1], want, nnum, tail[:32]))
    print("%-22s 对上 %d / 错配 %d / 无编号 %d" % (os.path.basename(path), ok, bad, skipped))
    for x in bad_samples:
        print("      x " + x)
    return bad


if __name__ == "__main__":
    files = sys.argv[1:] or sorted(
        glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out_*.epub")))
    total = sum(check(f) for f in files)
    print("-" * 60)
    print("错配合计 %d 组" % total)
    sys.exit(1 if total else 0)
