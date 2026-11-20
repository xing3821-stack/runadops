#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Put a person on each campaign, and let the alert panel filter to just theirs.
#
#   cd /var/www/runadops && python3 patch-owner.py index.html
#
# Needs patch-alerts.py first.
# Aborts without touching anything if an anchor is missing. Keeps a .bak-owner.
import io, os, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

if "memberSel" in s:
    print("Already patched, nothing to do."); raise SystemExit
if "function alertPanel(" not in s:
    print("ABORTED: 先跑 patch-alerts.py(要按人筛预警)")
    print("  python3 patch-alerts.py " + p)
    raise SystemExit(1)

E = []

# 1. 投放项目加操盘手
E.append((
    "    {k:'status',l:'状态',t:'select',opt:CAMP_STATUS.map(x=>x[0])},{k:'note',l:'备注',t:'textarea',full:1}",
    "    {k:'status',l:'状态',t:'select',opt:CAMP_STATUS.map(x=>x[0])},{k:'ownerId',l:'操盘手',t:'memberSel'},\n"
    "    {k:'note',l:'备注',t:'textarea',full:1}",
))

# 2. 表单里能选团队成员
E.append((
    "  else if(f.t==='creativeSel'){",
    "  else if(f.t==='memberSel'){const opts=(state.members||[]).map(m=>`<option value=\"${m.id}\" ${m.id===v?'selected':''}>${esc(m.name||m.email)}</option>`).join('');"
    "inner=`<select id=\"f_${f.k}\"><option value=\"\">—(没指定)</option>${opts}</select>`;}\n"
    "  else if(f.t==='creativeSel'){",
))

# 3. 成员名字
E.append((
    "function campName(id){",
    "function memberName(id){const m=(state.members||[]).find(x=>x.id===id);return m?(m.name||m.email):'';}\n"
    "function campName(id){",
))

# 4. 给项目产生的预警打上负责人
E.append((
    "  run.forEach(c=>{\n    const ds=dailiesOf(c.id);",
    "  run.forEach(c=>{\n"
    "    const _mark=out.length;   /* 这条项目产生的预警从这里开始，循环末尾统一打上负责人 */\n"
    "    const ds=dailiesOf(c.id);",
))
E.append((
    """    /* 过期:到点了还在投 */
    if(c.end && c.end<dstr(today)){
      out.push({level:'amber',tag:'过期',
        text:`${c.name} 结束日期 ${c.end} 已过,状态还是「进行中」`,
        go:`openForm('campaigns','${c.id}')`});
    }
  });""",
    """    /* 过期:到点了还在投 */
    if(c.end && c.end<dstr(today)){
      out.push({level:'amber',tag:'过期',
        text:`${c.name} 结束日期 ${c.end} 已过,状态还是「进行中」`,
        go:`openForm('campaigns','${c.id}')`});
    }
    for(let i=_mark;i<out.length;i++) out[i].who=c.ownerId||'';
  });""",
))

# 5. 面板加筛选
E.append((
    """function alertPanel(){
  const a=alerts();
  if(!a.length) return `<div class="section-note" style="border-left-color:var(--accent)">✓ 没有预警。在投项目都在记数、没超支、ROAS 和 CPA 都在线内。</div>`;
  const red=a.filter(x=>x.level==='red').length;
  const rows=a.map(x=>`<div class="mini" onclick="${x.go}" style="cursor:pointer">
      <span class="pill ${x.level==='red'?'p-red':'p-amber'}">${x.tag}</span>
      <div style="flex:1">${esc(x.text)}</div>
      <div class="cell-sub">去处理 →</div></div>`).join('');
  return `<div class="panel" style="margin-bottom:16px;border-color:${red?'var(--red)':'var(--amber)'}">
    <div class="panel-h"><h3>⚠ 需要处理 ${a.length} 条${red?` · 其中 ${red} 条紧急`:''}</h3></div>
    <div class="panel-b">${rows}</div></div>`;
}""",

    """let alertMine=false;   /* 预警面板:只看我负责的 */
function toggleAlertMine(){alertMine=!alertMine;render();}
function alertPanel(){
  const all=alerts();
  const me=user&&user.id;
  const mine=all.filter(x=>x.who&&x.who===me);
  const a=alertMine?mine:all;
  if(!all.length) return `<div class="section-note" style="border-left-color:var(--accent)">✓ 没有预警。在投项目都在记数、没超支、ROAS 和 CPA 都在线内。</div>`;
  const red=a.filter(x=>x.level==='red').length;
  const rows=a.length?a.map(x=>`<div class="mini" onclick="${x.go}" style="cursor:pointer">
      <span class="pill ${x.level==='red'?'p-red':'p-amber'}">${x.tag}</span>
      <div style="flex:1">${esc(x.text)}</div>
      <div class="cell-sub">${x.who?esc(memberName(x.who)):'未指定'} · 去处理 →</div></div>`).join('')
    :`<div class="empty" style="padding:24px">你负责的项目没有待处理的。</div>`;
  const btn=`<button class="btn ghost" style="padding:5px 11px;font-size:12px" onclick="toggleAlertMine()">${alertMine?'看全部 ('+all.length+')':'只看我的 ('+mine.length+')'}</button>`;
  return `<div class="panel" style="margin-bottom:16px;border-color:${red?'var(--red)':'var(--amber)'}">
    <div class="panel-h"><h3>⚠ ${alertMine?'我负责的':'需要处理'} ${a.length} 条${red?` · 其中 ${red} 条紧急`:''}</h3>
      <div class="spacer"></div>${btn}</div>
    <div class="panel-b">${rows}</div></div>`;
}""",
))

# 6. 投放项目列表显示操盘手
E.append((
    "<td><span class=\"pill ${pillClass(CAMP_STATUS,c.status)}\">${esc(c.status||'—')}</span></td></tr>`;}).join('');\n"
    "  return `<div class=\"card\"><div class=\"tbl-wrap\"><table><thead><tr><th>项目</th><th>平台</th><th>目标</th><th>预算</th>",

    "<td><span class=\"pill ${pillClass(CAMP_STATUS,c.status)}\">${esc(c.status||'—')}</span>"
    "${c.ownerId?`<div class=\"cell-sub\">${esc(memberName(c.ownerId))}</div>`:''}</td></tr>`;}).join('');\n"
    "  return `<div class=\"card\"><div class=\"tbl-wrap\"><table><thead><tr><th>项目</th><th>平台</th><th>目标</th><th>预算</th>",
))

missing = [i + 1 for i, (old, _) in enumerate(E) if s.count(old) != 1]
if missing:
    print("ABORTED, nothing changed. These anchors were not found exactly once:", missing)
    raise SystemExit(1)

out = s
for old, new in E:
    out = out.replace(old, new, 1)

if not os.path.exists(p + ".bak-owner"):
    shutil.copy2(p, p + ".bak-owner"); print("backup ->", p + ".bak-owner")
io.open(p, "w", encoding="utf-8").write(out)
print("操盘手 + 预警按人筛 added: %d -> %d bytes" % (len(s.encode()), len(out.encode())))
