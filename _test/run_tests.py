#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键回归测试。

    python _test/run_tests.py            # 用现有样本跑全部校验
    python _test/run_tests.py --regen    # 先重新生成样本，再跑校验

流程：样本 -> 三档转换（out_*.epub）-> 校验成书结构 -> 校验角标与注释编号配对。
任一环节失败就非 0 退出，方便接到 CI 里。
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable

SAMPLES = ["a", "b", "c", "d", "e", "f"]
STYLES = ["tight", "compact", "loose"]


def run(args, allow_fail=False):
    r = subprocess.run([PY] + args, cwd=ROOT)
    if r.returncode and not allow_fail:
        print("\n[FAIL] %s" % " ".join(args))
        sys.exit(r.returncode)
    return r.returncode


def clean():
    for f in glob.glob(os.path.join(HERE, "out_*.epub")):
        os.remove(f)


def main():
    regen = "--regen" in sys.argv

    if regen:
        print("=" * 60)
        print("重新生成样本")
        print("=" * 60)
        for s in ["make_samples.py", "make_sample_c.py", "make_sample_d.py",
                  "make_sample_e.py", "make_sample_f.py"]:
            run([os.path.join("_test", s)])

    clean()

    print("=" * 60)
    print("转换：%d 个样本 x %d 档" % (len(SAMPLES), len(STYLES)))
    print("=" * 60)
    for name in SAMPLES:
        src = os.path.join("_test", "sample_%s.epub" % name)
        if not os.path.exists(src):
            print("  [SKIP] 缺少 %s，加 --regen 重新生成" % src)
            continue
        for style in STYLES:
            out = os.path.join("_test", "out_%s_%s.epub" % (name, style))
            run(["epub_footnote_inline.py", src,
                 "-o", out, "--style", style, "--class-fallback"])

    print("=" * 60)
    print("校验成书结构")
    print("=" * 60)
    run([os.path.join("_test", "verify_outputs.py")])

    print("=" * 60)
    print("校验角标与注释编号配对")
    print("=" * 60)
    run([os.path.join("_test", "check_pairing.py")])

    print("=" * 60)
    print("全部通过")


if __name__ == "__main__":
    main()
