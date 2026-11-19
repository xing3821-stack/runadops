#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Add conversions / revenue / bridge-page fields to campaigns, and compute
# CPA + ROAS from them — in the campaign table and on the overview.
#
#   cd /var/www/runadops && python3 patch-metrics.py index.html
#
# Five edits:
#   1. campaigns schema: 转化数 / 转化价值 / 中间页
#   2. helper functions cpa() / roas() / roasClass()
#   3. campaign table: a "成本 / 回报" column (CPA + ROAS, colour-coded)
#   4. campaign table header
#   5. overview: two more KPI tiles (整体 ROAS, 平均 CPA)
#
# Aborts without touching anything if an anchor is missing.
# Keeps a .bak-metrics (never overwrites an existing one). Safe to run twice.
import io, os, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

if "function roas(" in s:
    print("Already patched, nothing to do."); raise SystemExit

EDITS = []

# 1. schema
EDITS.append((
    "    {k:'budget',l:'总预算 (U)',t:'number'},{k:'spent',l:'已花费 (U)',t:'number'},\n",
    "    {k:'budget',l:'总预算 (U)',t:'number'},{k:'spent',l:'已花费 (U)',t:'number'},\n"
    "    {k:'conversions',l:'转化数(成交/线索)',t:'number'},{k:'revenue',l:'转化价值 (U)',t:'number'},\n"
    "    {k:'bridge',l:'中间页地址',t:'text',full:1},\n",
))

# 2. helpers — put them next to the other small formatters
EDITS.append((
    "function fmt(n){n=Number(n)||0;return n.toLocaleString('en-US');}",
    "function fmt(n){n=Number(n)||0;return n.toLocaleString('en-US');}\n"
    "/* 单次成交成本:花出去的钱 ÷ 拿到的转化数 */\n"
    "function cpa(c){const sp=Number(c.spent)||0,cv=Number(c.conversions)||0;return cv>0?sp/cv:null;}\n"
    "/* 回报倍数:转化价值 ÷ 花出去的钱 */\n"
    "function roas(c){const sp=Number(c.spent)||0,rv=Number(c.revenue)||0;return sp>0&&rv>0?rv/sp:null;}\n"
    "/* 3 以上算好,1.5 以下该关掉 —— 和投放标准里的那条线一致 */\n"
    "function roasClass(r){return r==null?'':(r>=3?'p-green':(r<1.5?'p-red':'p-amber'));}\n"
    "function roasTxt(r){return r==null?'—':(Math.round(r*100)/100)+'x';}",
))

# 3. table cell: insert a new <td> right before the 周期 cell
EDITS.append((
    "<td class=\"cell-sub\">${esc(c.start||'')}${c.end?' → '+esc(c.end):''}</td>",
    "<td style=\"min-width:120px\">"
    "<div class=\"num\">${cpa(c)==null?'<span class=\"cell-sub\">转化数未填</span>':'CPA '+fmt(Math.round(cpa(c)*100)/100)+' '+CUR()}</div>"
    "<div style=\"margin-top:4px\">${roas(c)==null?'':'<span class=\"pill '+roasClass(roas(c))+'\">ROAS '+roasTxt(roas(c))+'</span>'}</div>"
    "</td>"
    "<td class=\"cell-sub\">${esc(c.start||'')}${c.end?' → '+esc(c.end):''}</td>",
))

# 4. header
EDITS.append((
    "<th>已花费 / 进度</th><th>周期</th>",
    "<th>已花费 / 进度</th><th>成本 / 回报</th><th>周期</th>",
))

# 5. overview tiles — appended after the 广告已花费 tile
EDITS.append((
    """    <div class="kpi"><div class="bar"></div><div class="lbl">◷ 广告已花费</div><div class="val">${fmt(mgSpent)}<small>${CUR()}</small></div><div class="meta">进行中项目累计</div></div>\n""",
    """    <div class="kpi"><div class="bar"></div><div class="lbl">◷ 广告已花费</div><div class="val">${fmt(mgSpent)}<small>${CUR()}</small></div><div class="meta">进行中项目累计</div></div>
    <div class="kpi ${mgRoas==null?'':(mgRoas>=3?'':(mgRoas<1.5?'amber':'blue'))}"><div class="bar"></div><div class="lbl">↗ 整体 ROAS</div><div class="val">${mgRoas==null?'—':roasTxt(mgRoas)}</div><div class="meta">${mgRev>0?'转化价值 '+fmt(mgRev)+' '+CUR():'填了转化价值才算得出'}</div></div>
    <div class="kpi blue"><div class="bar"></div><div class="lbl">◎ 平均 CPA</div><div class="val">${mgCpa==null?'—':fmt(Math.round(mgCpa*100)/100)}<small>${mgCpa==null?'':CUR()}</small></div><div class="meta">${mgConv>0?'共 '+fmt(mgConv)+' 个转化':'填了转化数才算得出'}</div></div>\n""",
))

# the overview needs those three numbers — compute them next to mgSpent
EDITS.append((
    "const mgBudget=run.reduce((s,c)=>s+(Number(c.budget)||0),0), mgSpent=run.reduce((s,c)=>s+(Number(c.spent)||0),0);",
    "const mgBudget=run.reduce((s,c)=>s+(Number(c.budget)||0),0), mgSpent=run.reduce((s,c)=>s+(Number(c.spent)||0),0);\n"
    "  const mgConv=run.reduce((s,c)=>s+(Number(c.conversions)||0),0), mgRev=run.reduce((s,c)=>s+(Number(c.revenue)||0),0);\n"
    "  const mgCpa=mgConv>0?mgSpent/mgConv:null, mgRoas=(mgSpent>0&&mgRev>0)?mgRev/mgSpent:null;",
))

missing = [i + 1 for i, (old, _) in enumerate(EDITS) if s.count(old) != 1]
if missing:
    print("ABORTED, nothing changed. These anchors were not found exactly once:", missing)
    raise SystemExit(1)

out = s
for old, new in EDITS:
    out = out.replace(old, new, 1)

if not os.path.exists(p + ".bak-metrics"):
    shutil.copy2(p, p + ".bak-metrics"); print("backup ->", p + ".bak-metrics")
io.open(p, "w", encoding="utf-8").write(out)
print("CPA / ROAS added: %d -> %d bytes" % (len(s.encode()), len(out.encode())))
