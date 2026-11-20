#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Turn "watch the ads by hand" into "the console watches, a person handles exceptions".
#
#   cd /var/www/runadops && python3 patch-alerts.py index.html
#
# Six rules, all computed from the daily rows + the campaign's own settings:
#   断更   在投项目最近 2 天没记数据
#   超支   已花费 >= 总预算的 90%
#   亏损   近 7 天 ROAS < 1.5
#   超标   近 7 天 CPA 高于该项目设的目标 CPA
#   过期   结束日期已过但状态还是进行中
#   逾期   待收款超过 30 天
#
# Shown as a panel at the top of 概览, each line opens the record it is about,
# plus a count badge on the 概览 nav item.
#
# Needs patch-daily.py first (the rules read the per-day rows).
# Aborts without touching anything if an anchor is missing.
# Keeps a .bak-alerts. Safe to run twice.
import io, os, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

if "function alerts(" in s:
    print("Already patched, nothing to do."); raise SystemExit

if "viewDailies" not in s:
    print("ABORTED: 先跑 patch-daily.py(预警要读按天数据)")
    print("  python3 patch-daily.py " + p)
    raise SystemExit(1)

E = []

# 1. 目标 CPA 字段 —— 没有它就没法判「超标」
E.append((
    "    {k:'bridge',l:'中间页地址',t:'text',full:1},\n",
    "    {k:'bridge',l:'中间页地址',t:'text',full:1},\n"
    "    {k:'targetCpa',l:'目标 CPA (U,超了报警)',t:'number'},\n",
))

# 2. 规则本体
ALERTS = r"""
/* ============ 预警 ============ */
/* 每条:{level:'red'|'amber', tag, text, go} —— go 是点了跳去哪 */
function alerts(){
  const out=[], today=Date.now();
  const run=state.campaigns.filter(c=>c.status==='进行中');

  run.forEach(c=>{
    const ds=dailiesOf(c.id);
    const R=rollup(c);

    /* 断更:最近两天一条都没记。没数据等于看不见,排第一 */
    const recent=ds.filter(d=>d.date>=dstr(today-1*DAY));
    if(ds.length && !recent.length){
      const last=ds[ds.length-1].date;
      const gap=Math.round((today-new Date(last).getTime())/DAY);
      out.push({level:gap>=3?'red':'amber',tag:'断更',
        text:`${c.name} 已经 ${gap} 天没记数据(最后一笔 ${last})`,go:"go('dailies')"});
    }
    if(!ds.length){
      out.push({level:'amber',tag:'断更',text:`${c.name} 在投但一天数据都没记`,go:"go('dailies')"});
    }

    /* 超支:预算快见底 */
    const bud=Number(c.budget)||0;
    if(bud>0 && R.spent>=bud*0.9){
      const pct=Math.round(R.spent/bud*100);
      out.push({level:pct>=100?'red':'amber',tag:'超支',
        text:`${c.name} 已花 ${fmt(Math.round(R.spent))} / ${fmt(bud)} ${CUR()}(${pct}%)`,
        go:`openForm('campaigns','${c.id}')`});
    }

    /* 近 7 天的表现:亏损 / CPA 超标 */
    const w=ds.filter(d=>d.date>=dstr(today-6*DAY));
    const wSpend=w.reduce((s,d)=>s+(Number(d.spend)||0),0);
    const wConv=w.reduce((s,d)=>s+(Number(d.conversions)||0),0);
    const wRev=w.reduce((s,d)=>s+(Number(d.revenue)||0),0);
    if(wSpend>0 && wRev>0 && wRev/wSpend<1.5){
      out.push({level:'red',tag:'亏损',
        text:`${c.name} 近 7 天 ROAS ${roasTxt(wRev/wSpend)},低于 1.5 —— 按投放标准该关掉`,
        go:`openForm('campaigns','${c.id}')`});
    }
    const tgt=Number(c.targetCpa)||0;
    if(tgt>0 && wConv>0){
      const cur=wSpend/wConv;
      if(cur>tgt){
        out.push({level:cur>tgt*1.5?'red':'amber',tag:'超标',
          text:`${c.name} 近 7 天 CPA ${fmt(Math.round(cur*100)/100)},目标 ${fmt(tgt)} ${CUR()}`,
          go:`openForm('campaigns','${c.id}')`});
      }
    }

    /* 过期:到点了还在投 */
    if(c.end && c.end<dstr(today)){
      out.push({level:'amber',tag:'过期',
        text:`${c.name} 结束日期 ${c.end} 已过,状态还是「进行中」`,
        go:`openForm('campaigns','${c.id}')`});
    }
  });

  /* 逾期未收 */
  state.payments.filter(p=>p.status==='待收').forEach(p=>{
    if(!p.date) return;
    const days=Math.round((today-new Date(p.date).getTime())/DAY);
    if(days>=30){
      out.push({level:days>=60?'red':'amber',tag:'逾期',
        text:`${clientName(p.clientId)} 一笔 ${fmt(p.amount)} ${CUR()} 待收已 ${days} 天`,
        go:`openForm('payments','${p.id}')`});
    }
  });

  return out.sort((a,b)=>(a.level==='red'?0:1)-(b.level==='red'?0:1));
}
function alertPanel(){
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
}
"""
E.append(("function viewOverview(){", ALERTS + "\nfunction viewOverview(){"))

# 3. 概览顶部插面板
E.append((
    "  return kpis+`<div class=\"prow\"><div class=\"panel\"><div class=\"panel-h\"><h3>▲ 进行中的投放</h3>",
    "  return alertPanel()+kpis+`<div class=\"prow\"><div class=\"panel\"><div class=\"panel-h\"><h3>▲ 进行中的投放</h3>",
))

# 4. 导航上给概览加个数字
E.append((
    "    const ct=t.coll?`<span class=\"ct\">${(state[t.coll]||[]).length}</span>`:(t.id==='team'?`<span class=\"ct\">${(state.members||[]).length}</span>`:'');",
    "    let ct=t.coll?`<span class=\"ct\">${(state[t.coll]||[]).length}</span>`:(t.id==='team'?`<span class=\"ct\">${(state.members||[]).length}</span>`:'');\n"
    "    if(t.id==='overview'){const n=(typeof alerts==='function')?alerts().length:0;"
    "ct=n?`<span class=\"ct\" style=\"background:var(--red-dim);color:var(--red)\">${n}</span>`:'';}",
))

missing = [i + 1 for i, (old, _) in enumerate(E) if s.count(old) != 1]
if missing:
    print("ABORTED, nothing changed. These anchors were not found exactly once:", missing)
    raise SystemExit(1)

out = s
for old, new in E:
    out = out.replace(old, new, 1)

if not os.path.exists(p + ".bak-alerts"):
    shutil.copy2(p, p + ".bak-alerts"); print("backup ->", p + ".bak-alerts")
io.open(p, "w", encoding="utf-8").write(out)
print("预警模块 added: %d -> %d bytes" % (len(s.encode()), len(out.encode())))
