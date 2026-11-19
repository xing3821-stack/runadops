#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 自建后端之后，团队页那段说明还在教人去 Supabase 后台，已经不对了。换成命令行的做法。
#   cd /var/www/runadops && python3 patch-team-note.py index.html
import io, os, re, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

NEW = ('团队成员用各自账号登录,看到<b>同一套数据</b>。'
       '<b>新增成员 / 改角色</b>:在服务器上执行<br>'
       '<code>cd /opt/runadops-api</code><br>'
       '<code>node server.js useradd 邮箱 密码 member</code> — 加人<br>'
       '<code>node server.js userrole 邮箱 admin</code> — 改角色<br>'
       '<code>node server.js passwd 邮箱 新密码</code> — 重置密码<br>'
       '<code>node server.js userlist</code> — 看都有谁<br>'
       '<b>owner / admin</b> 能删数据,<b>member</b> 只能增改(这条规则在服务端,绕不过去)。')

if 'node server.js useradd' in s:
    print("Already updated, nothing to do."); raise SystemExit

pat = re.compile(r'(function viewTeam\(\)\{\s*\n\s*const note=`<div class="section-note">)(.*?)(</div>`;)', re.S)
m = pat.search(s)
if not m:
    print("ABORTED: team note not found, nothing changed."); raise SystemExit(1)
if 'Supabase' not in m.group(2):
    print("ABORTED: the note does not mention Supabase, so this is not the expected version."); raise SystemExit(1)

out = s[:m.start(2)] + NEW + s[m.end(2):]
if not os.path.exists(p + ".bak-teamnote"):
    shutil.copy2(p, p + ".bak-teamnote"); print("backup ->", p + ".bak-teamnote")
io.open(p, "w", encoding="utf-8").write(out)
print("team note updated: %d -> %d bytes" % (len(s.encode()), len(out.encode())))
