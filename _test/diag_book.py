#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断真实书籍：为什么有些注释匹配不到正文角标。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import epub_footnote_inline as M

path = sys.argv[1]
book = M.EpubBook(path)

defs = M.collect_definitions(book)
ref_index = M.build_ref_index(book)
conv = M.Converter(book, "inline", False, False, False)

unmatched = []
for doc_name, el in defs:
    if conv.refs_for(doc_name, el):
        continue
    unmatched.append((doc_name, el))

print("总注释 %d，未匹配 %d" % (len(defs), len(unmatched)))

# 未匹配的注释都分布在哪些文件
from collections import Counter
c = Counter(n for n, _ in unmatched)
for n, k in c.most_common():
    print("  %-40s %d" % (n, k))

print("\n--- 前 5 条未匹配注释的开头文字与 id ---")
for doc_name, el in unmatched[:5]:
    print("  id=%-16s %s" % (el.get("id"), repr(M.element_text(el)[:50])))

print("\n--- 前 5 条【能匹配】的注释的 id ---")
matched = [(n, e) for n, e in defs if conv.refs_for(n, e)]
for doc_name, el in matched[:5]:
    print("  id=%-16s %s" % (el.get("id"), repr(M.element_text(el)[:50])))

# 引用 index 里关键 target 的数量
print("\n--- ref index 里出现最多的 target 文档 ---")
c2 = Counter(k[0] for k in ref_index)
for n, k in c2.most_common(5):
    print("  %-40s %d 个锚点" % (n, k))

# 未匹配注释所在文件，看看这些文件在 ref index 里有没有被指向
print("\n--- 未匹配注释所在文件，是否被正文链接指向 ---")
for doc_name, _ in unmatched[:5]:
    hits = sum(1 for k in ref_index if k[0] == doc_name)
    print("  %-40s 被指向 %d 次" % (doc_name, hits))
