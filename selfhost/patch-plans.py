#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Give packages a billing period and a platform coverage, so short-cycle plans
# (7-day / 30-day, per platform or bundled) can be priced in the console.
#
#   cd /var/www/runadops && python3 patch-plans.py index.html
#
# Three edits:
#   1. packages schema: 周期 / 覆盖平台 / 包含服务
#   2. 计费方式 gains 周期套餐
#   3. package cards show the period and the platform tags
#
# Aborts without touching anything if an anchor is missing.
# Keeps a .bak-plans (never overwrites an existing one). Safe to run twice.
import io, os, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

if "PKG_PERIODS" in s:
    print("Already patched, nothing to do."); raise SystemExit

E = []

# 1. 周期选项常量，放在 BILLINGS 旁边
E.append((
    "const BILLINGS=['月费','一次性','按广告花费%'];",
    "const BILLINGS=['周期套餐','月费','一次性','按广告花费%'];\n"
    "const PKG_PERIODS=['7 天','14 天','30 天','1 个月','3 个月','6 个月','一次性'];",
))

# 2. schema
E.append((
    "  packages:[\n"
    "    {k:'name',l:'套餐名',t:'text',req:1,full:1},{k:'billing',l:'计费方式',t:'select',opt:BILLINGS},\n"
    "    {k:'price',l:'价格 (U 或 %)',t:'number'},{k:'desc',l:'说明',t:'textarea',full:1}\n"
    "  ],",

    "  packages:[\n"
    "    {k:'name',l:'套餐名',t:'text',req:1,full:1},{k:'billing',l:'计费方式',t:'select',opt:BILLINGS},\n"
    "    {k:'price',l:'价格 (U 或 %)',t:'number'},{k:'period',l:'周期',t:'select',opt:PKG_PERIODS},\n"
    "    {k:'platforms',l:'覆盖平台',t:'checks',opt:PLATFORMS,full:1},\n"
    "    {k:'includes',l:'包含服务(一行一条)',t:'textarea',full:1},\n"
    "    {k:'desc',l:'说明',t:'textarea',full:1}\n"
    "  ],",
))

# 3. 卡片上把周期和平台显示出来
E.append((
    "const cards=state.packages.map(p=>{const unit=p.billing==='按广告花费%'?'%':' '+CUR();"
    "const bl={'月费':'/ 月','一次性':'一次性','按广告花费%':'of 广告花费'}[p.billing]||'';"
    "return `<div class=\"pkg\" onclick=\"openForm('packages','${p.id}')\">"
    "<div class=\"pn\">${esc(p.name)}</div><div class=\"pp\">${fmt(p.price)}${unit}</div>"
    "<div class=\"pb\">${esc(bl)}</div><div class=\"pd\">${esc(p.desc||'')}</div></div>`;}).join('');",

    "const cards=state.packages.map(p=>{const unit=p.billing==='按广告花费%'?'%':' '+CUR();"
    "const bl=p.billing==='周期套餐'?(p.period?('/ '+esc(p.period)):'周期套餐')"
    ":({'月费':'/ 月','一次性':'一次性','按广告花费%':'of 广告花费'}[p.billing]||'');"
    "const plats=(p.platforms||[]).map(x=>`<span class=\"tag b\">${esc(x)}</span>`).join('');"
    "const inc=(p.includes||'').split('\\n').map(x=>x.trim()).filter(Boolean);"
    "const incHtml=inc.length?`<div class=\"pd\" style=\"margin-top:8px\">`+inc.map(x=>`<div>· ${esc(x)}</div>`).join('')+`</div>`:'';"
    "return `<div class=\"pkg\" onclick=\"openForm('packages','${p.id}')\">"
    "<div class=\"pn\">${esc(p.name)}</div><div class=\"pp\">${fmt(p.price)}${unit}</div>"
    "<div class=\"pb\">${bl}</div>"
    "${plats?`<div style=\"margin-top:8px\">${plats}</div>`:''}"
    "${incHtml}"
    "${p.desc?`<div class=\"pd\" style=\"margin-top:8px\">${esc(p.desc)}</div>`:''}</div>`;}).join('');",
))

missing = [i + 1 for i, (old, _) in enumerate(E) if s.count(old) != 1]
if missing:
    print("ABORTED, nothing changed. These anchors were not found exactly once:", missing)
    raise SystemExit(1)

out = s
for old, new in E:
    out = out.replace(old, new, 1)

if not os.path.exists(p + ".bak-plans"):
    shutil.copy2(p, p + ".bak-plans"); print("backup ->", p + ".bak-plans")
io.open(p, "w", encoding="utf-8").write(out)
print("套餐加了周期/平台/包含服务: %d -> %d bytes" % (len(s.encode()), len(out.encode())))
