#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_footnote_inline.py
把 EPUB 里的「弹窗脚注 / 跳转尾注」改写成「正文内嵌注」。

背景
----
Kindle 原生阅读器（含 PW5）没有任何"脚注常驻页底"的开关：脚注是弹窗还是跳转，
完全由书籍自身的标记决定 —— <aside epub:type="footnote"> 就会被渲染成弹窗。
Send to Kindle 推送的 EPUB 会在亚马逊服务器转成 KFX，这一步同样由标记驱动。
所以越狱 / KUAL 在原生阅读器上帮不上忙，可行做法是：在推送之前改书。

本脚本在电脑上把每条脚注的内容从「文末注释区」搬到「引用它的那段正文下面」，
变成普通正文块，并抹掉 epub:type 语义。这样 Kindle 转 KFX 后它就是普通段落，
直接显示在你读到的位置上，不需要点击。

用法
----
  python epub_footnote_inline.py 书.epub
  python epub_footnote_inline.py 书.epub -o 新书.epub
  python epub_footnote_inline.py *.epub --style tight

脚注会被插在「引用它的那个段落」后面，默认带上正文角标里那个编号。

依赖：pip install lxml
"""

from __future__ import annotations

import argparse
import copy
import html.entities
import os
import posixpath
import re
import sys
import zipfile
from urllib.parse import unquote

try:
    from lxml import etree
except ImportError:  # pragma: no cover
    sys.exit("缺少 lxml，请先执行：  pip install lxml")


# ---------------------------------------------------------------- 常量

OPF_NS = "http://www.idpf.org/2007/opf"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
EPUB_NS = "http://www.idpf.org/2007/ops"
EPUB_TYPE_ATTR = "{%s}type" % EPUB_NS
DOC_MARK_ATTR = "data-kfxdoc"     # 临时标记：反查元素属于哪个 xhtml，序列化前摘掉
DEF_MARK_ATTR = "data-kfxdef"     # 临时标记：标出注释定义，扫角标时用来排除回跳链接
DEF_KEY_ATTR = "data-kfxdefkey"   # 临时标记：定义的稳定身份，避免插入节点后 XPath 改变
REF_MARK_ATTR = "data-kfxref"     # 临时标记：排文档顺序时标出待排的角标，排完摘掉

BLOCK_TAGS = {
    "p", "div", "li", "dd", "dt", "blockquote", "q",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "pre", "table", "section", "aside", "article", "figure", "figcaption",
    "ul", "ol", "dl", "hr", "center", "main", "header", "footer", "nav",
    "form", "fieldset", "details", "summary", "body", "html",
}
# 这些标签内部不能直接插入块级元素，遇到就往上浮
CLIMB_TAGS = {"td", "th", "tr", "tbody", "thead", "tfoot", "li", "dd", "dt"}

NOTE_TYPE_WORDS = ("footnote", "endnote", "rearnote", "doc-note", "doc-footnote", "doc-endnote")
BACKLINK_WORDS = ("noteref", "backlink", "footnote-back", "duokan-footnote-back", "return", "reversefootnote")
BACKLINK_GLYPHS = ("↩", "↗", "↖", "◄", "«", "<<", "[返回]", "返回")

CLASS_DEF_RE = re.compile(
    r"(?<![\w-])(footnote|endnote|rearnote|fn|note|fnote|noteitem|duokan-footnote-item)(?![\w-])",
    re.I,
)

# 把 noteContent / note-content / NOTE_ITEM 这类拼接写法切成单词
_CLASS_WORD_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z]+|[0-9]+")
# 这些词出现在类名里说明它是正文角标 / 回跳链接，不是注释定义
_CLASS_REF_WORD_RE = re.compile(r"ref|marker|superscript|subscript|sub|sup", re.I)
NOTE_CLASS_WORDS = ("footnote", "endnote", "rearnote", "note", "fnote", "noteitem")

# 全小写直接拼在一起的写法（notecontent）。只认后面接"内容/条目"这类后缀，
# 免得把 noteref、notes 这种角标或复数容器也算成注释定义。
_CLASS_CONCAT_RE = re.compile(
    r"(?<![a-z])(?:footnote|endnote|rearnote|note|fnote)"
    r"(?:content|item|text|body|list|block|entry)(?![a-z])", re.I)


def looks_like_note_class(cls: str) -> bool:
    """
    类名是不是"这是一条注释"的意思。

    CLASS_DEF_RE 只认独立单词（class="footnote"），但很多中文书用拼接写法，
    比如《红楼梦》校注本是驼峰的 class="noteContent"，于是 note 后面紧跟大写 C，
    独立单词那条判断就落空了。这里把类名按驼峰 / 连字符 / 下划线切成单词再比对。

    反过来 noteref、noteRef、note-marker 是正文角标，必须排除，
    否则会把角标当成注释定义，整本书的正文都被搬走。
    """
    if not cls:
        return False
    if CLASS_DEF_RE.search(cls) or _CLASS_CONCAT_RE.search(cls):
        return True
    words = [w.lower() for w in _CLASS_WORD_RE.findall(cls)]
    if not words:
        return False
    if any(_CLASS_REF_WORD_RE.search(w) for w in words):
        return False
    return any(w in NOTE_CLASS_WORDS for w in words)

# 三档紧凑度预设：tight 最省地方（纯缩进，无竖线），compact 带一条细竖线，loose 最宽松
STYLE_PRESETS = {
    "tight": """
.kfx-inline-note{font-size:0.78em;line-height:1;margin:0.1em 0 0.22em 0;padding:0 0 0 1.2em;text-align:justify;text-indent:0;page-break-inside:avoid;}
.kfx-inline-note p,.kfx-inline-note div,.kfx-inline-note li{margin:0;line-height:1;text-indent:0;}
.kfx-inline-note ol,.kfx-inline-note ul{list-style:none;margin:0;padding:0;text-indent:0;}
.kfx-inline-note a{text-decoration:none;}
.kfx-note-marker{font-size:0.72em;vertical-align:super;line-height:1;}
.kfx-note-label{font-size:0.92em;margin-right:0.2em;}
.kfx-note-adjacent{margin-top:0;}
""",
    "compact": """
.kfx-inline-note{font-size:0.82em;line-height:1;margin:0.2em 0 0.35em 0;padding:0.05em 0 0.05em 0.5em;border-left:2px solid #9a9a9a;text-align:justify;text-indent:0;page-break-inside:avoid;}
.kfx-inline-note p,.kfx-inline-note div,.kfx-inline-note li{margin:0 0 0.08em 0;line-height:1;text-indent:0;}
.kfx-inline-note ol,.kfx-inline-note ul{list-style:none;margin:0;padding:0;text-indent:0;}
.kfx-inline-note a{text-decoration:none;}
.kfx-note-marker{font-size:0.72em;vertical-align:super;line-height:1;}
.kfx-note-label{font-size:0.92em;margin-right:0.25em;}
.kfx-note-adjacent{margin-top:0.05em;}
""",
    "loose": """
.kfx-inline-note{font-size:0.85em;line-height:1.35;margin:0.6em 0 0.9em 0;padding:0.3em 0 0.3em 0.85em;border-left:2px solid #9a9a9a;text-align:justify;text-indent:0;page-break-inside:avoid;}
.kfx-inline-note p,.kfx-inline-note div,.kfx-inline-note li{margin:0.2em 0;line-height:1.35;text-indent:0;}
.kfx-inline-note ol,.kfx-inline-note ul{list-style:none;margin:0;padding:0;text-indent:0;}
.kfx-inline-note a{text-decoration:none;}
.kfx-note-marker{font-size:0.72em;vertical-align:super;line-height:1;}
.kfx-note-label{font-size:0.92em;margin-right:0.25em;}
.kfx-note-adjacent{margin-top:0.25em;}
""",
}
DEFAULT_STYLE = "compact"
INLINE_CSS = STYLE_PRESETS[DEFAULT_STYLE]


# ---------------------------------------------------------------- 小工具

def lname(el) -> str:
    """元素标签的本地名（去掉 {namespace} 前缀，统一小写）"""
    t = el.tag
    if not isinstance(t, str):
        return ""
    return t.rsplit("}", 1)[-1].lower()


def retag(el, new_name: str):
    """换标签名，但保持原来的命名空间（XHTML 里不能换成无命名空间的裸标签）"""
    t = el.tag
    if isinstance(t, str) and t.startswith("{"):
        el.tag = "{%s}%s" % (t[1:].split("}", 1)[0], new_name)
    else:
        el.tag = new_name


def epub_type_of(el) -> str:
    """读取 epub:type / role，小写返回"""
    v = el.get(EPUB_TYPE_ATTR)
    if v is None:
        v = el.get("epub:type")
    if v is None:
        v = el.get("role")
    if v is None:
        v = el.get("type")
    return (v or "").lower()


def _ent_repl(m):
    body = m.group(1)
    if body.startswith("#"):
        return m.group(0)
    ch = html.entities.html5.get(body + ";") or html.entities.html5.get(body)
    if ch is None:
        return m.group(0)
    return "".join("&#%d;" % ord(c) for c in ch)


_ENT_RE = re.compile(r"&(#?[A-Za-z0-9]+);")
_XMLDECL_ENC_RE = re.compile(r"(<\?xml[^>]*?)\s+encoding\s*=\s*[\"'][^\"']*[\"']", re.I)

# HTML 里的"空元素"，EPUB 要求自闭合；不规范的书常写成 <br> 之类，解析前先补上
HTML_VOID = ("br", "hr", "img", "meta", "link", "input", "col", "area", "base",
             "embed", "param", "source", "track", "wbr")
_VOID_RE = re.compile(r"<(%s)\b([^>]*?)(?<!/)>" % "|".join(HTML_VOID), re.I)


def repair_void_tags(text: str) -> str:
    return _VOID_RE.sub(lambda m: "<%s%s/>" % (m.group(1), m.group(2)), text)


def extract_doctype(raw: str):
    """原样保留源文件里的 DOCTYPE 声明，没有就返回 None"""
    i = raw[:2000].lower().find("<!doctype")
    if i < 0:
        return None
    j = raw.find(">", i)
    return raw[i:j + 1] if j > 0 else None


def make_parser():
    return etree.XMLParser(
        recover=True,
        huge_tree=True,
        resolve_entities=False,   # 防 XXE；命名实体已预先转成数字引用
        load_dtd=False,
        no_network=True,
    )


def normalize_xhtml_source(text: str) -> str:
    text = _XMLDECL_ENC_RE.sub(lambda m: m.group(1), text, count=1)
    return _ENT_RE.sub(_ent_repl, text)


def drop_element(el):
    """删除元素但保留它的 tail 文本"""
    parent = el.getparent()
    if parent is None:
        return
    tail = el.tail or ""
    prev = el.getprevious()
    if prev is not None:
        prev.tail = (prev.tail or "") + tail
    else:
        parent.text = (parent.text or "") + tail
    parent.remove(el)


def unwrap_element(el):
    """
    把 el 从树上摘掉，用它的内容顶替它的位置（text / tail 都保留）。
    跟 drop_element 的区别：drop 是连内容一起扔，unwrap 是只脱掉外壳。
    """
    parent = el.getparent()
    if parent is None:
        return False
    idx = parent.index(el)
    head = el.text or ""
    tail = el.tail or ""
    children = list(el)
    prev = el.getprevious()

    if children:
        first = children[0]
        if head.strip():
            first.text = head + (first.text or "")
        elif head:
            # 纯空白：塞回上一层，别把词与词之间的空格吃掉
            if prev is not None:
                prev.tail = (prev.tail or "") + head
            else:
                parent.text = (parent.text or "") + head
        last = children[-1]
        last.tail = (last.tail or "") + tail
        for off, c in enumerate(children):
            parent.insert(idx + off, c)
    else:
        chunk = head + tail
        if prev is not None:
            prev.tail = (prev.tail or "") + chunk
        else:
            parent.text = (parent.text or "") + chunk
    parent.remove(el)
    return True


def element_text(el) -> str:
    return "".join(el.itertext())


# 多看/微信读书之类把注释塞进 <ol class="duokan-footnote-content"><li class="duokan-footnote-item">，
# 类名里出现这些词就认定它只是包装，而不是作者真的在注释里写了个列表
LIST_WRAP_CLASS_RE = re.compile(
    r"(duokan|footnote|endnote|rearnote|noteitem|fnote|(?:^|[\s-])fn(?:[\s-]|$))", re.I)


def flatten_note_wrapper(note) -> bool:
    """
    拆掉注释块里那层没语义的包装标签，让注释直接躺在 .kfx-inline-note 下：

        <div class="kfx-inline-note"><ol class="duokan-footnote-content">
            <li class="duokan-footnote-item">正文…</li></ol></div>
      → <div class="kfx-inline-note">正文…</div>

    ol/ul 默认带 padding-left 和项目符号，li 自带 margin —— 留着它们，
    每条注释前后都会被撑开一大截，看着就是"注释之间空得离谱"。
    """
    changed = False
    for _ in range(6):                      # 有些书套了两三层
        if len(note) != 1:
            break
        child = note[0]
        if not isinstance(child.tag, str):
            break
        tag = lname(child)
        if tag in ("ol", "ul"):
            items = [c for c in child
                     if isinstance(c.tag, str) and lname(c) == "li"]
            # 只有一条 li，或类名长得像注释容器，才认定是包装；
            # 作者真的在注释里列了 3 条的，原样保留列表语义
            if len(items) > 1 and not LIST_WRAP_CLASS_RE.search(child.get("class") or ""):
                break
        elif tag == "li":
            pass
        elif tag == "div":
            # 没 class / 没 id / 没 style 的裸 div 也是纯包装
            if child.get("class") or child.get("id") or child.get("style"):
                break
        else:
            break
        if not unwrap_element(child):
            break
        changed = True
    return changed


_CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNIT = {"十": 10, "百": 100, "千": 1000}
_NUM_TOKEN_RE = re.compile(
    r"(\d+|[一二三四五六七八九十百千万零〇两]+|"
    r"[\u2460-\u2473\u3251-\u325f\u32b1-\u32bf]+)")


def _cn_number(tok: str):
    """把 '一' / '十' / '二十一' 这样的中文数字转成阿拉伯数字字符串"""
    section = num = 0
    found = False
    for ch in tok:
        if ch in _CN_DIGIT:
            found = True
            num = _CN_DIGIT[ch]
        elif ch in _CN_UNIT:
            found = True
            section += (num if num else 1) * _CN_UNIT[ch]
            num = 0
        else:
            break
    return str(section + num) if found else None


# 编号前面可能出现的括号、点、顿号之类
_LEAD_PUNCT_RE = re.compile(
    r"^[\s　\[\]【】〔〕()（）<>《》「」『』⟦⟧\{\}\.、:：,，;；]{0,6}")


def note_number_of(s: str):
    """
    取一段文字**开头**那个编号的序号字符串，取不到返回 None。
    只认"剥掉开头括号标点后紧跟着的第一个编号"，这样 "第一条：…" 里的"一"
    不会被误判成编号，而 "【3】正文…"、"1848 年…" 能正确识别。
    """
    if not s:
        return None
    rest = s[_LEAD_PUNCT_RE.match(s).end():]
    m = _NUM_TOKEN_RE.match(rest)
    if not m:
        return None
    tok = m.group(1)
    # 注意不能用 isdigit()：'①' 之类的圈码也返回 True，但 int() 会炸
    if tok.isascii() and tok.isdecimal():
        return str(int(tok))                       # 去掉前导 0，方便比较
    cp = ord(tok[0])
    if 0x2460 <= cp <= 0x2473:                     # ① … ⑳
        return str(cp - 0x2460 + 1)
    if 0x3251 <= cp <= 0x325F:                     # ㉑ … ㉟
        return str(cp - 0x3251 + 1)
    if 0x32B1 <= cp <= 0x32BF:                     # ㊱ … ㊿
        return str(cp - 0x32B1 + 1)
    return _cn_number(tok)


def prepend_label(note, label: str):
    """把脚注标号塞到注释正文最前面"""
    span = etree.Element(
        "{%s}span" % note.tag[1:].split("}", 1)[0] if note.tag.startswith("{") else "span")
    span.set("class", "kfx-note-label")
    span.text = label

    if note.text and note.text.strip():
        span.tail = note.text.lstrip()
        note.text = None
        note.insert(0, span)
        return

    # 正文在子元素里（比如 <p>），钻到第一个真正有文字的地方
    target = note
    while len(target) and not (target.text and target.text.strip()):
        target = target[0]
    if target.text and target.text.strip():
        span.tail = target.text.lstrip()
        target.text = None
        target.insert(0, span)
    else:
        target.text = label


# 没有文字内容的"空壳"标签，容器里只剩它们时也视为空
VOID_TAGS = {"hr", "br", "img", "wbr", "col"}

# 单独成页、且只剩下这种标题的注释页，可以整页丢掉
NOTE_HEADING_RE = re.compile(
    r"^[\s　]*(注\s*释|注\s*文|脚\s*注|尾\s*注|译\s*注|notes?|footnotes?|endnotes?|"
    r"notes?\s*(and|&)\s*sources?|references?)[\s　]*$", re.I)


def is_empty_container(el) -> bool:
    for c in el:
        if isinstance(c.tag, str) and lname(c) not in VOID_TAGS:
            return False
        if (c.tail or "").strip():
            return False
    if (el.text or "").strip():
        return False
    return True


def clean_lonely_note_heading(doc: "XHTMLDoc"):
    """注释页搬空后，把孤零零的『注释』标题也删掉"""
    body = doc.body
    if body is None:
        return
    kids = [c for c in body if isinstance(c.tag, str)]
    if len(kids) != 1:
        return
    h = kids[0]
    if lname(h) not in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div"):
        return
    if (h.tail or "").strip():
        return
    if not NOTE_HEADING_RE.match(element_text(h) or ""):
        return
    body.remove(h)
    doc.dirty = True


# ---------------------------------------------------------------- 文档模型

class XHTMLDoc:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self.dirty = False
        self.xml_mode = True
        raw = data.decode("utf-8", errors="replace")
        self.doctype = extract_doctype(raw)

        # 先按严格 XML 解析（能完整保留命名空间）
        src = repair_void_tags(normalize_xhtml_source(raw))
        root = etree.fromstring(src.encode("utf-8"), make_parser())
        if root is None or lname(root) != "html" or self._has_broken_void(root):
            # 不规范的书：退回 HTML 解析器（会自动补全 <br>、大小写、实体）
            self.xml_mode = False
            from lxml import html as lxml_html
            root = lxml_html.document_fromstring(raw)
            if root is None:
                raise ValueError("无法解析：%s" % name)
        self.tree = root.getroottree()
        self.root = root
        self.body = self._find_body()
        self.id_map = {}
        if self.body is not None:
            for el in self.body.iter():
                i = el.get("id")
                if i:
                    self.id_map[i] = el

    def _find_body(self):
        for el in self.root.iter():
            if lname(el) == "body":
                return el
        return None

    @staticmethod
    def _has_broken_void(root) -> bool:
        """XML 容错解析有时会把 <br> 后面的内容当成它的子节点，说明源文件不规范"""
        for el in root.iter():
            if lname(el) in HTML_VOID and len(el) > 0:
                return True
        return False

    def head(self):
        for el in self.root.iter():
            if lname(el) == "head":
                return el
        return None

    def to_bytes(self) -> bytes:
        kw = {"xml_declaration": True, "encoding": "UTF-8"}
        if self.doctype:
            kw["doctype"] = self.doctype
        if not self.xml_mode:
            kw["method"] = "xml"      # HTML 解析出来的树也要按 XML 规则自闭合输出
        return etree.tostring(self.tree, **kw)


# ---------------------------------------------------------------- EPUB 容器

class EpubBook:
    def __init__(self, path: str, use_class_fallback: bool = False):
        self.path = path
        self.use_class_fallback = use_class_fallback
        self.zf = zipfile.ZipFile(path, "r")
        self.docs = {}          # name -> XHTMLDoc
        self.doc_order = []     # 阅读顺序
        self._load()

    # -- 基础读 ---------------------------------------------------
    def _load(self):
        opf_path = self._opf_path()
        opf_dir = posixpath.dirname(opf_path)
        opf = etree.fromstring(self.zf.read(opf_path), make_parser())

        manifest = {}
        for item in opf.iter():
            if lname(item) == "item":
                iid = item.get("id")
                href = item.get("href")
                mtype = (item.get("media-type") or "").lower()
                if iid and href:
                    manifest[iid] = (posixpath.normpath(posixpath.join(opf_dir, unquote(href))), mtype)

        spine_ids = []
        for item in opf.iter():
            if lname(item) == "itemref":
                idref = item.get("idref")
                if idref and (item.get("linear") or "yes").lower() != "no":
                    spine_ids.append(idref)

        spine_files = [manifest[i][0] for i in spine_ids if i in manifest]
        all_files = [v[0] for v in manifest.values()
                     if v[1] in ("application/xhtml+xml", "text/html", "text/x-oeb1-document")]

        # 正文文档按 spine 顺序，其余文档排在后面
        ordered = spine_files + [f for f in all_files if f not in spine_files]
        for f in ordered:
            if f in self.docs:
                continue
            try:
                data = self.zf.read(f)
            except KeyError:
                continue
            try:
                self.docs[f] = XHTMLDoc(f, data)
            except Exception as exc:                      # noqa: BLE001
                print("  ! 跳过无法解析的文件 %s (%s)" % (f, exc))
        self.doc_order = list(self.docs.keys())
        self.spine_files = [f for f in spine_files if f in self.docs]

    def _opf_path(self) -> str:
        data = self.zf.read("META-INF/container.xml")
        root = etree.fromstring(data, make_parser())
        for el in root.iter():
            if lname(el) == "rootfile":
                return unquote(el.get("full-path"))
        raise ValueError("找不到 OPF：%s" % self.path)

    def close(self):
        self.zf.close()

    def current_bytes(self, name: str, changed: dict) -> bytes:
        """取文件当前内容：改过的用新内容，没改的读原始 zip"""
        if name in changed:
            return changed[name]
        return self.zf.read(name)

    def plan_file_drops(self, changed: dict):
        """
        找出被搬空、且全书再没有任何地方链接到的 XHTML，
        返回 (要删除的文件名集合, 重新生成后的 OPF 字节 or None)
        """
        candidates = [
            n for n, d in self.docs.items()
            if d.body is not None and d.dirty and is_empty_container(d.body)
        ]
        opf_path = self._opf_path()          # OPF 本身当然会列出它，不算"被引用"
        dropped = set()
        for name in candidates:
            base = posixpath.basename(name).encode("utf-8")
            referenced = False
            for other in self.zf.namelist():
                if other == name or other == opf_path:
                    continue
                try:
                    data = self.current_bytes(other, changed)
                except KeyError:
                    continue
                if base in data:
                    referenced = True
                    break
            if not referenced:
                dropped.add(name)
        if not dropped:
            return set(), None
        return dropped, self._rewrite_opf(dropped)

    def _rewrite_opf(self, dropped: set):
        path = self._opf_path()
        root = etree.fromstring(self.zf.read(path), make_parser())
        drop_ids = set()
        for item in root.iter():
            if lname(item) == "item":
                href = unquote(item.get("href") or "")
                full = posixpath.normpath(posixpath.join(posixpath.dirname(path), href))
                if full in dropped:
                    drop_ids.add(item.get("id"))

        removables = [el for el in root.iter()
                      if (lname(el) == "itemref" and el.get("idref") in drop_ids)
                      or (lname(el) == "item" and el.get("id") in drop_ids)]
        for el in removables:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    def write(self, out_path: str, changed: dict, removed: set):
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
            zi = zipfile.ZipInfo("mimetype")
            zi.compress_type = zipfile.ZIP_STORED
            try:
                zout.writestr(zi, self.zf.read("mimetype"))
            except KeyError:
                zout.writestr(zi, b"application/epub+zip")
            for item in self.zf.infolist():
                if item.filename == "mimetype" or item.filename in removed:
                    continue
                data = changed.get(item.filename)
                if data is None:
                    data = self.zf.read(item.filename)
                zout.writestr(item, data)


# ---------------------------------------------------------------- 脚注识别

def looks_like_definition(el, use_class_fallback: bool) -> bool:
    if lname(el) == "a":
        return False
    et = epub_type_of(el)
    if et:
        if any(w in et for w in NOTE_TYPE_WORDS):
            return True
        if "note" in et and "noteref" not in et and "biblioentry" not in et:
            return True
    if (el.get("type") or "").lower() in ("footnote", "endnote", "rearnote"):
        return True
    if use_class_fallback:
        # 许多老书把注释写成 class="fnote" / class="footnote" / class="noteContent"，
        # 但把 id 放在注释块内部的回跳 <a> 上，而不是放在外层 <p> 上。
        # 因此不能再要求外层元素必须有 id；后续会从内部锚点 id 反查正文角标。
        cls = el.get("class") or ""
        if cls and looks_like_note_class(cls):
            return True
    return False


def looks_like_backlink(el) -> bool:
    et = epub_type_of(el)
    if et and any(w in et for w in BACKLINK_WORDS):
        return True
    cls = (el.get("class") or "").lower()
    if any(w in cls for w in ("backlink", "footnote-back", "reversefootnote", "noteref-back")):
        return True
    txt = (element_text(el) or "").strip()
    if txt in BACKLINK_GLYPHS:
        return True
    if txt and len(txt) <= 6 and any(g in txt for g in ("↩", "↗", "↖", "◄")):
        return True
    return False


# 链接文字只有一个脚注编号：[1] / (1) / ① / 一
_MARKER_ONLY_RE = re.compile(
    r"^[\[\(（【〔]?\s*"
    r"(\d{1,4}|[一二三四五六七八九十百千万]{1,6}"
    r"|[\u2460-\u2473\u3251-\u325f\u32b1-\u32bf]{1,2})"
    r"\s*[\]\)）】〕]?[.、．]?$")


def is_dead_backlink(el) -> bool:
    """
    判定「这就是回跳角标，丢掉」—— 只看注释块内部的 <a>。

    书里链接错位时（比如注释[1]的回跳其实指向 noteref-5-11，跟本条注释的角标对不上），
    按 id 匹配是抓不到的；但这类链接有个铁特征：站内跳转 + 链接文字只有个编号。
    外链（http / mailto）一律不动，那可能是注释里的引用出处。
    """
    href = (el.get("href") or "").strip()
    if href.startswith(("http://", "https://", "mailto:", "ftp://")):
        return False
    if not href.startswith("#"):
        return False
    return bool(_MARKER_ONLY_RE.match((element_text(el) or "").strip()))


def collect_definitions(book: EpubBook):
    """返回 [(doc_name, element)]，已剔除"容器套容器"的外层"""
    found = []
    for name in book.doc_order:
        doc = book.docs[name]
        if doc.body is None:
            continue
        for el in doc.body.iter():
            if looks_like_definition(el, book.use_class_fallback):
                found.append((name, el))

    # lxml 元素代理的 id() 不稳定；跨文档用「文件名 + 树内路径」做节点身份。
    found_set = {(name, el.getroottree().getpath(el)) for name, el in found}
    # 若某个定义内部还嵌着别的定义，只保留最内层
    inner = []
    for name, el in found:
        has_inner = any((name, el.getroottree().getpath(c)) in found_set
                        for c in el.iter() if c is not el)
        if not has_inner:
            inner.append((name, el))

    # 外层容器（如 <ol class="footnotes">）里每个带 id 的子项各自成一条注
    exploded = []
    for name, el in inner:
        doc = book.docs[name]
        children = [c for c in el if isinstance(c.tag, str) and c.get("id")]
        if len(children) >= 2 and not any(epub_type_of(c) for c in children):
            for c in children:
                exploded.append((name, c))
        else:
            exploded.append((name, el))
    return exploded


def build_ref_index(book: EpubBook):
    """(目标文档, 锚点id) -> [<a> 元素列表]"""
    index = {}
    for name in book.doc_order:
        doc = book.docs[name]
        if doc.body is None:
            continue
        for a in doc.body.iter():
            if lname(a) != "a":
                continue
            href = (a.get("href") or "").strip()
            if not href or "#" not in href:
                continue
            path, _, frag = href.partition("#")
            frag = unquote(frag)
            if not frag:
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(path))) if path else name
            index.setdefault((target, frag), []).append(a)
    return index


def build_marker_number_index(book: EpubBook, defs):
    """
    (文档名, 编号字符串) -> [正文角标 <a>, ...]

    有些书（多看 / 微信读书导出的很常见）注释条目上压根没写 id，
    或者回跳链接是死的 href="#"，按 id 就永远配不上。
    但注释正文和正文角标都带着同一个编号（[67] / 67 / ①），
    所以再建一份"按编号"的索引兜底。

    索引只收**注释区以外**的链接，注释内部那个回跳链接（文字也是 [67]）必须排除，
    否则会自己配自己。做法是扫描前给注释元素临时打标记，扫完再摘掉。
    """
    for _, el in defs:
        el.set(DEF_MARK_ATTR, "1")
    index = {}
    try:
        for name in book.doc_order:
            doc = book.docs[name]
            if doc.body is None:
                continue
            for a in doc.body.iter():
                if lname(a) != "a":
                    continue
                if a.get(DEF_MARK_ATTR):
                    continue
                if any(anc.get(DEF_MARK_ATTR) for anc in a.iterancestors()):
                    continue
                href = (a.get("href") or "").strip()
                if not href or href == "#":        # 死链（多看那些空回跳）
                    continue
                num = note_number_of(element_text(a).strip())
                if num is None:
                    continue
                index.setdefault((name, num), []).append(a)
    finally:
        for _, el in defs:
            if DEF_MARK_ATTR in el.attrib:
                del el.attrib[DEF_MARK_ATTR]
    return index


# ---------------------------------------------------------------- 插入位置

def insertion_anchor(a):
    """找到应该把脚注插在它后面的那个块级元素"""
    node = a
    while node is not None and lname(node) not in BLOCK_TAGS:
        node = node.getparent()
    while node is not None and lname(node) in CLIMB_TAGS:
        parent = node.getparent()
        if parent is None or lname(parent) in ("body", "html"):
            break
        node = parent
    return node


# ---------------------------------------------------------------- 核心转换

class Converter:
    """把弹窗脚注搬进正文：每条注释插到引用它的那个段落后面"""
    def __init__(self, book: EpubBook, keep_endnotes: bool,
                 keep_marker_link: bool, use_class_fallback: bool,
                 add_label: bool = True, style: str = DEFAULT_STYLE,
                 trust_links: bool = False):
        self.book = book
        self.style_css = STYLE_PRESETS.get(style, STYLE_PRESETS[DEFAULT_STYLE])
        self.keep_endnotes = keep_endnotes
        self.keep_marker_link = keep_marker_link
        self.use_class_fallback = use_class_fallback
        self.add_label = add_label
        self.trust_links = trust_links
        self.ref_index = build_ref_index(book)
        self.defs = collect_definitions(book)
        for i, (_, el) in enumerate(self.defs):
            el.set(DEF_KEY_ATTR, "kfxdef-%d" % i)
        self.marker_by_number = build_marker_number_index(book, self.defs)
        self.pairing = None         # (文档名, 树内路径) -> [正文角标 <a>]，首次用时现算
        self.stats_fixed = 0        # 链接错位、按编号改配的条数
        self.stats_added = 0        # 没有链接、按编号补配的条数
        self.stats = {"defs": 0, "matched": 0, "inserted": 0, "unmatched": 0}
        self.counter = 0
        self._last_insert = {}     # (文档名, 锚点路径) -> 最后插入的元素
        self.doc_order = {f: i for i, f in enumerate(book.doc_order)}
        self._mark_docs()
        self._mark_defs()

    def _mark_defs(self):
        """
        给注释定义**和它的所有祖先**打标记。

        用途有两个：判断「这个角标是不是在注释区里」（不该被当成正文引用），
        以及块模式下把文末那一整块注释容器从切块范围里排除掉。
        """
        for _, el in self.defs:
            node = el
            # 到 body/html 就别往上标了：body 带上了这个标记，
            # _inside_def 会对全文都返回 True，正文角标就被全当成"注释区里的"排掉了
            while node is not None and lname(node) not in ("body", "html"):
                if node.get(DEF_MARK_ATTR):
                    break
                node.set(DEF_MARK_ATTR, "1")
                node = node.getparent()

    # -- 文档身份 -------------------------------------------------
    def _mark_docs(self):
        """
        给每份文档的根节点打一个临时标记，用来反查"这个元素属于哪个文件"。

        不能像以前那样用 id(root) 当字典 key：lxml 每次访问元素都会生成新的代理对象，
        没人持有的话立刻被回收，地址随后被别的元素复用，查出来就是错的文档
        （实际表现是：注释被插进完全不相干的章节里）。
        打个属性最省事也最可靠，序列化前摘掉就行。
        """
        self.token_to_doc = {}
        self._roots = []           # 持有 root 代理，防止被回收
        for i, (name, doc) in enumerate(self.book.docs.items()):
            root = doc.root
            if root is None:
                continue
            token = "kfxdoc-%d" % i
            root.set(DOC_MARK_ATTR, token)
            self.token_to_doc[token] = name
            self._roots.append(root)

    def unmark_docs(self):
        """序列化前把临时标记摘掉，别留在成书里"""
        for root in getattr(self, "_roots", []):
            if DOC_MARK_ATTR in root.attrib:
                del root.attrib[DOC_MARK_ATTR]
        marks = (DEF_MARK_ATTR, DEF_KEY_ATTR, REF_MARK_ATTR)
        for doc in self.book.docs.values():
            root = getattr(doc, "root", None)
            if root is None:
                continue
            for el in root.iter():
                if not isinstance(el.tag, str):
                    continue
                for attr in marks:
                    if attr in el.attrib:
                        del el.attrib[attr]

    def _doc_of(self, el):
        root = el.getroottree().getroot()
        return self.token_to_doc.get(root.get(DOC_MARK_ATTR), "")

    def _node_key(self, el):
        """元素的当前位置：文档名 + 文档内 XPath。"""
        return (self._doc_of(el), el.getroottree().getpath(el))

    def _def_key(self, el):
        """定义的稳定身份。插入正文节点后，定义的 XPath 可能变化，所以使用临时 token。"""
        token = el.get(DEF_KEY_ATTR)
        return token if token else self._node_key(el)

    # -- 找引用 ---------------------------------------------------
    def refs_for(self, doc_name, el):
        if self.pairing is None:
            self.plan_pairing()
        refs = list(self.pairing.get(self._def_key(el)) or [])
        refs.sort(key=lambda a: (self.doc_order.get(self._doc_of(a), 9999), self._seq_of(a)))
        return refs

    def _refs_direct(self, doc_name, el):
        """按定义自身或内部回跳锚点的 id 反查正文角标，再退回回跳链接。"""
        # 规范 EPUB 通常把 id 放在 <aside> 上；老式转换书则常把 id 放在
        # 注释块内部的第一个 <a> 上，例如：
        #   <p class="fnote"><a id="ch53">(53)</a> ...</p>
        # 正文里的 href 会直接指向 part0057.html#ch53，因此这里必须同时查
        # 外层 id 和内部锚点 id，且允许目标文档与注释定义文档不同。
        ids = []
        nid = el.get("id")
        if nid:
            ids.append(nid)
        for node in el.iter():
            if lname(node) == "a" and node.get("id"):
                if node.get("id") not in ids:
                    ids.append(node.get("id"))

        refs = []
        seen = set()
        for frag in ids:
            for a in self.ref_index.get((doc_name, frag), []):
                if self._inside_def(a):
                    continue
                key = self._marker_key(a)
                if key not in seen:
                    seen.add(key)
                    refs.append(a)
        if not refs:
            refs = self._refs_via_backlink(el)
        refs.sort(key=lambda a: (self.doc_order.get(self._doc_of(a), 9999), self._seq_of(a)))
        return refs

    def _marker_key(self, a):
        """角标的唯一身份：lxml 的代理对象 id 不稳定，得用 (文档, 树内路径)"""
        return (self._doc_of(a), a.getroottree().getpath(a))

    def _marker_num(self, a):
        return note_number_of(element_text(a).strip())

    def plan_pairing(self):
        """
        决定每条注释该配到哪个正文角标上。

        为什么要绕这一圈：很多书（多看导出的尤其常见）里，注释条目上的 id 和
        正文角标的 href 是错位的 —— 角标 [32] 指向的注释内容其实是 [20]。
        照着链接走，就会把错误的注释插进正文，比不处理还糟。

        所以策略是**编号优先、链接兜底**：
          1. 先按 id / 回跳链接找；如果角标上的编号和注释自己的编号对得上，就信它。
          2. 对不上的（链接错位）—— 不认，改按编号重新找一个还没被占用的角标。
          3. 压根没有链接的（注释条目没写 id）—— 同样按编号补配。
        只在同一个 xhtml 内配对，跨文件配错的风险太大，宁可不配。
        """
        direct = {}
        for doc_name, el in self.defs:
            direct[self._def_key(el)] = self._refs_direct(doc_name, el)

        if self.trust_links:
            self.pairing = {k: v for k, v in direct.items() if v}
            self.stats_fixed = self.stats_added = 0
            return 0

        final = {}
        used = set()

        # 第 1 轮：链接和编号一致的最可信，先占住角标
        for doc_name, el in self.defs:
            key = self._def_key(el)
            refs = direct[key]
            if not refs:
                continue
            nnum = note_number_of(element_text(el)[:20])
            if nnum is None:
                # 注释没有编号可比对，只能信链接
                final[key] = refs
                for a in refs:
                    used.add(self._marker_key(a))
                continue
            ok = [a for a in refs if self._marker_num(a) == nnum]
            if ok:
                final[key] = ok
                for a in ok:
                    used.add(self._marker_key(a))
            # 一个都对不上的先空着，等第 2 轮按编号补

        # 第 2 轮：链接错位 / 压根没链接的，按编号配
        seq = {}
        fixed = added = 0
        for doc_name, el in self.defs:
            key = self._def_key(el)
            if key in final:
                continue
            nnum = note_number_of(element_text(el)[:20])
            if nnum is None:
                # 取不到编号，又没对上链接 —— 退回信链接，总比丢掉强
                if direct[key]:
                    final[key] = direct[key]
                continue
            k = seq.get((doc_name, nnum), 0)
            seq[(doc_name, nnum)] = k + 1
            cands = [a for a in self.marker_by_number.get((doc_name, nnum), [])
                     if self._marker_key(a) not in used]
            if k < len(cands):
                a = cands[k]
                final[key] = [a]
                used.add(self._marker_key(a))
                fixed += 1 if direct[key] else 0
                added += 0 if direct[key] else 1
            elif direct[key]:
                # 编号也配不上，还是信原链接
                final[key] = direct[key]

        self.pairing = final
        self.stats_fixed = fixed
        self.stats_added = added
        return fixed + added

    def _seq_of(self, el):
        """粗略的文档序号（只用来给同一条注释的多个角标排序，别拿它做全局排序）"""
        n = 0
        cur = el
        while cur is not None:
            prev = cur.getprevious()
            while prev is not None:
                n += 1
                prev = prev.getprevious()
            cur = cur.getparent()
        return n

    def reading_order(self, elements):
        """
        按**真实文档顺序**给一批元素编号，返回 {文档+路径: 序号}。

        不能用 _seq_of 顶替：它只是"各层前面兄弟数之和"，对不同嵌套深度的元素根本不可比 ——
        <p><span><sup> 里的角标算出 4，而 <p><sup> 里的算出 3，明明前者在文档里更靠前。
        结果就是注释插进正文时顺序整个乱掉（[7][8][9] 排成 [8][9][7]）。

        这里改成老老实实按文档序遍历一遍：先给待排元素打临时标记，
        边遍历边发号，排完把标记摘掉。
        """
        by_doc = {}
        for el in elements:
            by_doc.setdefault(self._doc_of(el), []).append(el)

        order = {}
        for doc_name, els in by_doc.items():
            if len(els) == 1:
                order[self._node_key(els[0])] = 0
                continue
            doc = self.book.docs.get(doc_name)
            if doc is None or doc.body is None:
                for i, el in enumerate(els):
                    order[self._node_key(el)] = i
                continue
            for el in els:
                el.set(REF_MARK_ATTR, "1")
            try:
                i = 0
                for e in doc.body.iter():
                    if REF_MARK_ATTR in e.attrib:
                        order[self._node_key(e)] = i
                        i += 1
                # 万一有角标没被遍历到（比如在 body 之外），兜底给个号
                for el in els:
                    order.setdefault(self._node_key(el), i)
                    i += 1
            finally:
                for el in els:
                    if REF_MARK_ATTR in el.attrib:
                        del el.attrib[REF_MARK_ATTR]
        return order

    def _inside_def(self, el):
        cur = el
        while cur is not None and lname(cur) not in ("body", "html"):
            # 定义和祖先都带有临时属性，不能依赖会随插入变化的 XPath。
            if cur.get(DEF_MARK_ATTR) or cur.get(DEF_KEY_ATTR):
                return True
            cur = cur.getparent()
        return False

    def _refs_via_backlink(self, el):
        """注释里没有正向引用时，靠它内部的回跳链接反查正文里的标记"""
        refs = []
        doc_name = self._doc_of(el)
        for a in el.iter():
            if lname(a) != "a":
                continue
            href = (a.get("href") or "").strip()
            if "#" not in href:
                continue
            path, _, frag = href.partition("#")
            frag = unquote(frag)
            if not frag:
                continue
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(doc_name), unquote(path))) if path else doc_name
            cand = self.book.docs.get(target)
            if cand is None:
                continue
            marker = cand.id_map.get(frag)
            if marker is not None and lname(marker) == "a" and not self._inside_def(marker):
                refs.append(marker)
        return refs

    # -- 造内嵌注 -------------------------------------------------
    def build_note(self, el, new_id, marker_ids, label=""):
        note = copy.deepcopy(el)
        if lname(note) in ("aside", "li", "section"):
            retag(note, "div")
        for attr in (EPUB_TYPE_ATTR, "epub:type", "role", "type"):
            if attr in note.attrib:
                del note.attrib[attr]
        note.set("id", new_id)
        cls = (note.get("class") or "").strip()
        note.set("class", (cls + " kfx-inline-note").strip())

        # 拆掉 <ol class="duokan-footnote-content"><li class="duokan-footnote-item"> 这类
        # 包装层：列表默认缩进 + 项目符号，是注释块被撑高的大头
        flatten_note_wrapper(note)

        # 去掉回跳链接
        for a in list(note.iter()):
            if lname(a) != "a":
                continue
            href = (a.get("href") or "").strip()
            frag = unquote(href.partition("#")[2])
            if looks_like_backlink(a) or (frag and frag in marker_ids) \
                    or is_dead_backlink(a):
                drop_element(a)

        # 补上脚注标号（正文开头已经有同样编号就不重复加）
        if label and self.add_label:
            head = element_text(note)[:20]
            key = note_number_of(label)
            if key is None or key != note_number_of(head):
                prepend_label(note, label)
        return note

    def insert_note(self, ref, note):
        doc = self.book.docs.get(self._doc_of(ref))
        if doc is None or doc.body is None:
            return False

        anchor = insertion_anchor(ref)
        if anchor is None or anchor is doc.body:
            doc.body.append(note)
        else:
            # 同一段引用多条注时，按引用顺序依次排在后面，并收紧它们之间的间距。
            # key 必须是「文档名 + 树内路径」：光用 getpath() 会跨文件撞车 ——
            # 每个 xhtml 里都有 /html/body/div/p[5]，结果就是后面章节的注释
            # 全被挂到先处理的那个文件的同路径元素后面去了。
            key = (self._doc_of(anchor), anchor.getroottree().getpath(anchor))
            last = self._last_insert.get(key)
            if last is not None and last.getparent() is not None:
                last.addnext(note)
                note.set("class", (note.get("class") or "") + " kfx-note-adjacent")
            else:
                anchor.addnext(note)
            self._last_insert[key] = note
        doc.dirty = True
        return True

    def rewrite_marker(self, ref, new_id):
        text = element_text(ref)
        if self.keep_marker_link:
            for attr in (EPUB_TYPE_ATTR, "epub:type", "role", "type"):
                if attr in ref.attrib:
                    del ref.attrib[attr]
            ref.set("href", "#" + new_id)
            ref.set("class", ((ref.get("class") or "") + " kfx-note-marker").strip())
        else:
            retag(ref, "sup")
            for k in list(ref.attrib.keys()):
                del ref.attrib[k]
            ref.set("class", "kfx-note-marker")
            # 原书角标常见为 <a><sup>(1)</sup></a>。只改外层标签而不清掉
            # 子 sup，会得到 <sup>(1)<sup>(1)</sup></sup>，正文就会显示两个编号。
            # 展平为单层 sup，并保留子元素尾部空白，避免吞掉正文间距。
            child_tail = "".join(c.tail or "" for c in list(ref))
            for child in list(ref):
                ref.remove(child)
            ref.text = text or ""
            if child_tail:
                ref.tail = child_tail + (ref.tail or "")

    # -- 清场 -----------------------------------------------------
    def prune_empty_from(self, node, body):
        """从 node 开始向上，把变空的容器一级级删掉"""
        cur = node
        while cur is not None and cur is not body and is_empty_container(cur):
            parent = cur.getparent()
            if parent is None:
                break
            # 带 id 的节点可能是目录/链接目标，留着空壳也比坏链安全
            if parent is body and cur.get("id"):
                break
            parent.remove(cur)
            cur = parent

    # -- 主流程 ---------------------------------------------------
    def run(self):
        # 1) 先把所有 (注释定义, 引用标记) 配对收集起来
        pairs = []
        meta = {}          # (定义文档, 定义路径) -> (文档名, 标记id集合)
        self.plan_pairing()
        if self.stats_fixed:
            print("  链接错位、按编号改配：%d 条" % self.stats_fixed)
        if self.stats_added:
            print("  注释没写链接、按编号补配：%d 条" % self.stats_added)
        for doc_name, el in self.defs:
            self.stats["defs"] += 1
            refs = self.refs_for(doc_name, el)
            if not refs:
                self.stats["unmatched"] += 1
                continue
            self.stats["matched"] += 1
            marker_ids = {r.get("id") for r in refs if r.get("id")}
            meta[self._def_key(el)] = (doc_name, marker_ids)
            for ref in refs:
                pairs.append((el, ref))

        # 2) 按正文阅读顺序插入，保证编号连续
        order = self.reading_order([p[1] for p in pairs])
        pairs.sort(key=lambda p: (self.doc_order.get(self._doc_of(p[1]), 9999),
                                  order.get(self._node_key(p[1]), 0)))

        # 3) 一条条插到引用它的那个段落后面
        for el, ref in pairs:
            self.counter += 1
            new_id = "kfxnote-%d" % self.counter
            doc_name, marker_ids = meta[self._def_key(el)]
            label = element_text(ref).strip()      # 正文中那个角标的文字，如 [1]
            note = self.build_note(el, new_id, marker_ids, label)
            if self.insert_note(ref, note):
                self.stats["inserted"] += 1
                self.rewrite_marker(ref, new_id)

        # 4) 删掉文末注释区（可选保留）
        if not self.keep_endnotes:
            for doc_name, el in self.defs:
                if self._def_key(el) not in meta:
                    continue
                doc = self.book.docs[doc_name]
                parent = el.getparent()
                drop_element(el)
                doc.dirty = True
                if parent is not None:
                    self.prune_empty_from(parent, doc.body)

        self._inject_css()
        self.unmark_docs()      # 临时标记别留在成书里
        return self.stats

    def _inject_css(self):
        for name, doc in self.book.docs.items():
            if not doc.dirty:
                continue
            head = doc.head()
            if head is None:
                continue
            for st in head:
                if lname(st) == "style" and "kfx-inline-note" in (st.text or ""):
                    break
            else:
                style = etree.SubElement(head, "style")
                style.set("type", "text/css")
                style.text = self.style_css


# ---------------------------------------------------------------- CLI

def convert_file(src: str, dst: str, keep_endnotes: bool,
                 keep_marker_link: bool, use_class_fallback: bool,
                 drop_empty_files: bool = True, add_label: bool = True,
                 style: str = DEFAULT_STYLE, trust_links: bool = False) -> dict:
    book = EpubBook(src, use_class_fallback=use_class_fallback)
    try:
        conv = Converter(book, keep_endnotes, keep_marker_link,
                         use_class_fallback, add_label=add_label, style=style,
                         trust_links=trust_links)
        stats = conv.run()

        if drop_empty_files:
            for doc in book.docs.values():
                if doc.dirty:
                    clean_lonely_note_heading(doc)

        changed = {n: d.to_bytes() for n, d in book.docs.items() if d.dirty}
        dropped = set()
        if drop_empty_files:
            dropped, opf_bytes = book.plan_file_drops(changed)
            if opf_bytes is not None:
                changed[book._opf_path()] = opf_bytes
            stats["dropped_files"] = sorted(dropped)
        book.write(dst, changed, dropped)
        return stats
    finally:
        book.close()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把 EPUB 的弹窗脚注改写成正文内嵌注（供 Kindle / Send to Kindle 使用）")
    ap.add_argument("inputs", nargs="+", help="一个或多个 .epub 文件")
    ap.add_argument("-o", "--output", help="输出文件（单文件输入时可用）")
    ap.add_argument("--suffix", default="-inline", help="未指定 -o 时的文件名后缀")
    ap.add_argument("--keep-endnotes", action="store_true",
                    help="保留文末注释区（脚注会出现两次）")
    ap.add_argument("--keep-marker-link", action="store_true",
                    help="保留角标链接（默认改成不可点的上标）")
    ap.add_argument("--class-fallback", action="store_true",
                    help="连 class~=footnote/note 的容器也当作脚注（标记不规范的书用）")
    ap.add_argument("--no-drop-empty-file", action="store_true",
                    help="保留被搬空后的『注释』页（默认会自动从书里移除）")
    ap.add_argument("--style", choices=("tight", "compact", "loose"), default=DEFAULT_STYLE,
                    help="紧凑度：tight 最省地方 / compact 默认 / loose 最宽松")
    ap.add_argument("--no-label", action="store_true",
                    help="注释前面不加脚注标号（默认会加上正文角标里的那个号）")
    ap.add_argument("--trust-links", action="store_true",
                    help="完全相信书里的链接，不做编号校正（怀疑配错了再用这个）")
    args = ap.parse_args(argv)

    exit_code = 0
    for src in args.inputs:
        if not os.path.isfile(src):
            print("跳过（文件不存在）：%s" % src)
            exit_code = 1
            continue
        if args.output and len(args.inputs) == 1:
            dst = args.output
        else:
            base, ext = os.path.splitext(src)
            dst = base + args.suffix + ext
        print("处理：%s" % os.path.basename(src))
        try:
            stats = convert_file(src, dst, args.keep_endnotes,
                                 args.keep_marker_link, args.class_fallback,
                                 drop_empty_files=not args.no_drop_empty_file,
                                 add_label=not args.no_label, style=args.style,
                                 trust_links=args.trust_links)
        except Exception as exc:                          # noqa: BLE001
            print("  失败：%s" % exc)
            exit_code = 1
            continue
        print("  识别脚注 %d 条 / 命中引用 %d 条 / 内嵌插入 %d 块 / 未匹配 %d 条"
              % (stats["defs"], stats["matched"], stats["inserted"],
                 stats["unmatched"]))
        if stats.get("dropped_files"):
            print("  已移除搬空的注释页：%s" % "、".join(stats["dropped_files"]))
        if stats["inserted"] == 0:
            print("  提示：没有脚注被改写。试试加 --class-fallback。")
        print("  输出：%s" % dst)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
