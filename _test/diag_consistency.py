#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计：按 id 链接配出来的「注释编号 vs 角标编号」是否一致。"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import epub_footnote_inline as M

path = sys.argv[1]
book = M.EpubBook(path)
defs = M.collect_definitions(book)
conv = M.Converter(book, "inline", False, False, False)

same = diff = noid = 0
samples = []

for doc_name, el in defs:
    refs = conv._refs_direct(doc_name, el)
    if not refs:
        continue
    note_num = M.note_number_of(M.element_text(el)[:20])
    for a in refs:
        mk_num = M.note_number_of(M.element_text(a).strip())
        if note_num is None or mk_num is None:
            noid += 1
            continue
        if note_num == mk_num:
            same += 1
        else:
            diff += 1
            if len(samples) < 8:
                samples.append((doc_name, mk_num, note_num,
                                M.element_text(el)[:34]))

total = same + diff
print("可按编号比对的配对：%d" % total)
print("  编号一致（链接正确）：%d  (%.1f%%)" % (same, 100.0 * same / max(total, 1)))
print("  编号不一致（链接错位）：%d  (%.1f%%)" % (diff, 100.0 * diff / max(total, 1)))
print("  取不到编号：%d" % noid)

if samples:
    print("\n错位样例（角标编号 -> 实际插入的注释编号）：")
    for d, mk, nt, txt in samples:
        print("  %-28s 角标[%s] -> 注释[%s] %r" % (os.path.basename(d), mk, nt, txt))
