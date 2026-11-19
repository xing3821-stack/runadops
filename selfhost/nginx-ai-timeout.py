#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 /api/ 的 proxy_read_timeout 调大。

AI 生成一次要半分钟到一分多钟,默认那个 60s 会在模型还没写完时就被 nginx 切断,
浏览器收到 504,但后端其实还在跑、钱照花。调到 300s。

  python3 nginx-ai-timeout.py /etc/nginx/sites-available/runadops.com [秒数]

只改 location /api/ 这一段里的那一行,找不到就中止。改完由调用方跑 nginx -t。
"""
import io
import os
import re
import shutil
import sys
import time


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/etc/nginx/sites-available/runadops.com"
    secs = sys.argv[2] if len(sys.argv) > 2 else "300"

    if not os.path.isfile(path):
        sys.exit("找不到配置文件: %s" % path)
    with io.open(path, encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()

    m = re.search(r"location\s+/api/\s*\{", text)
    if not m:
        sys.exit("中止:没找到 location /api/,没有改动")

    # 取出这个 location 块
    start = m.start()
    depth = 0
    i = text.index("{", start)
    end = None
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                end = j
                break
    if end is None:
        sys.exit("中止:location /api/ 的括号没闭合,没有改动")

    block = text[start:end + 1]
    cur = re.search(r"proxy_read_timeout\s+(\d+)s?\s*;", block)
    if cur and cur.group(1) == str(secs):
        print("已经是 %ss 了,不用改" % secs)
        return 0

    if cur:
        new_block = block[:cur.start()] + ("proxy_read_timeout %ss;" % secs) + block[cur.end():]
        what = "把 proxy_read_timeout 从 %ss 改成 %ss" % (cur.group(1), secs)
    else:
        new_block = block[:-1].rstrip() + ("\n        proxy_read_timeout %ss;\n    }" % secs)
        what = "加上 proxy_read_timeout %ss" % secs

    bak = "%s.bak-aitimeout-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, bak)
    with io.open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text[:start] + new_block + text[end + 1:])
    print("已备份 ->", bak)
    print(what)
    print("BACKUP=%s" % bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
