#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
往 runadops.com 的 nginx 配置里加一段 /api/ 反向代理。

  python3 nginx-add-api.py /etc/nginx/sites-available/runadops.com [port]

安全措施:
  - 只改传进来的这一个文件,绝不碰其他站点
  - 改之前先备份成 <文件>.bak-<时间戳>
  - 只往「listen 443」那个 server 块里插
  - 已经有 location /api/ 就直接退出,不重复插
  - 找不到预期结构就中止,什么都不改
写完由调用方跑 nginx -t 验证,不通过就还原备份。
"""
import os
import re
import shutil
import sys
import time

BLOCK = """
    # 操盘控制台后端(Node 服务跑在 127.0.0.1:{port})
    location /api/ {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }}
"""


def server_blocks(text):
    """找出所有顶层 server {...} 块,返回 (开始位置, 结束位置) —— 结束位置是那个右花括号的下标。"""
    out = []
    for m in re.finditer(r'\bserver\s*\{', text):
        depth = 0
        i = text.index('{', m.start())
        j = i
        while j < len(text):
            c = text[j]
            if c == '#':                       # 注释,跳到行尾
                nl = text.find('\n', j)
                j = len(text) if nl < 0 else nl
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    out.append((m.start(), j))
                    break
            j += 1
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/etc/nginx/sites-available/runadops.com"
    port = sys.argv[2] if len(sys.argv) > 2 else "8788"

    if not os.path.isfile(path):
        sys.exit("找不到配置文件: %s" % path)
    text = io_read(path)

    if re.search(r'location\s+/api/', text):
        print("已经配过 /api/ 转发了,不用重复加")
        return 0

    blocks = server_blocks(text)
    if not blocks:
        sys.exit("中止:这个文件里没找到 server 块,没有改动")

    # 选 listen 443 的那个;没有就退而求其次选最大的那个
    target = None
    for start, end in blocks:
        body = text[start:end]
        if re.search(r'listen\s[^;]*443', body):
            target = (start, end)
            break
    if target is None:
        sys.exit("中止:没找到监听 443 的 server 块,没有改动")

    start, end = target
    new_text = text[:end] + BLOCK.format(port=port) + text[end:]

    bak = "%s.bak-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, bak)
    io_write(path, new_text)
    print("已备份 ->", bak)
    print("已在 listen 443 的 server 块里加入 location /api/ -> 127.0.0.1:%s" % port)
    print("BACKUP=%s" % bak)      # 调用方用这行拿备份路径,校验失败好还原
    return 0


def io_read(p):
    with open(p, "r", encoding="utf-8", errors="surrogateescape") as f:
        return f.read()


def io_write(p, s):
    with open(p, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(s)


if __name__ == "__main__":
    sys.exit(main())
