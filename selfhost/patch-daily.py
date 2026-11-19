#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Add a "daily numbers" module: spend / conversions / revenue per campaign per day.
#
#   cd /var/www/runadops && python3 patch-daily.py index.html
#
# Why this one first: every number in the console is a single overwritten value,
# so there is no history — no trend, no week-over-week, no monthly report, no
# pacing alert. Those all need per-day rows underneath them. This adds that layer.
#
# What it adds:
#   1. record type `daily` {campaignId, date, spend, conversions, revenue, note}
#   2. a 每日数据 tab: entry form, table, 14-day trend chart (hand-drawn SVG)
#   3. campaign rows roll up their daily rows (falls back to the typed-in totals)
#   4. overview: this week vs last week on spend / conversions / revenue
#
# Aborts without touching anything if an anchor is missing.
# Keeps a .bak-daily (never overwrites an existing one). Safe to run twice.
import io, os, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

if "viewDailies" in s:
    print("Already patched, nothing to do."); raise SystemExit

E = []

# ---- 1. 类型表 + state ----
E.append((
    "const COLL_TYPE={clients:'client',campaigns:'campaign',payments:'payment',packages:'package',briefs:'brief'};\n"
    "const TYPE_COLL={client:'clients',campaign:'campaigns',payment:'payments',package:'packages',brief:'briefs'};\n"
    "let state={clients:[],campaigns:[],payments:[],packages:[],briefs:[],members:[],settings:{cur:'U'}};",

    "const COLL_TYPE={clients:'client',campaigns:'campaign',payments:'payment',packages:'package',briefs:'brief',dailies:'daily'};\n"
    "const TYPE_COLL={client:'clients',campaign:'campaigns',payment:'payments',package:'packages',brief:'briefs',daily:'dailies'};\n"
    "let state={clients:[],campaigns:[],payments:[],packages:[],briefs:[],dailies:[],members:[],settings:{cur:'U'}};",
))

# ---- 2. 导航 ----
E.append((
    "  {id:'campaigns',name:'投放项目',ic:'▲',coll:'campaigns'},\n",
    "  {id:'campaigns',name:'投放项目',ic:'▲',coll:'campaigns'},\n"
    "  {id:'dailies',name:'每日数据',ic:'◷',coll:'dailies'},\n",
))

# ---- 3. render 里的三张表 ----
E.append((
    "  ['clients','campaigns','payments','packages','briefs','members'].forEach(k=>{if(!Array.isArray(state[k]))state[k]=[];});",
    "  ['clients','campaigns','payments','packages','briefs','dailies','members'].forEach(k=>{if(!Array.isArray(state[k]))state[k]=[];});",
))
E.append((
    "campaigns:['投放项目','盯住每条广告的预算与进度'],",
    "campaigns:['投放项目','盯住每条广告的预算与进度'],dailies:['每日数据','按天记消耗和转化 —— 趋势、周环比、月报都靠它'],",
))
E.append((
    "const addLabels={clients:'+ 新增客户',briefs:'+ 新增配置',campaigns:'+ 新增投放',payments:'+ 记一笔收款',packages:'+ 新增套餐'};",
    "const addLabels={clients:'+ 新增客户',briefs:'+ 新增配置',campaigns:'+ 新增投放',payments:'+ 记一笔收款',packages:'+ 新增套餐',dailies:'+ 记一天数据'};",
))
E.append((
    "const V={overview:viewOverview,clients:viewClients,briefs:viewBriefs,campaigns:viewCampaigns,",
    "const V={overview:viewOverview,clients:viewClients,briefs:viewBriefs,campaigns:viewCampaigns,dailies:viewDailies,",
))

# ---- 4. 表单字段 ----
E.append((
    "  payments:[\n    {k:'clientId',l:'客户',t:'clientSel',req:1,full:1},",
    "  dailies:[\n"
    "    {k:'campaignId',l:'投放项目',t:'campaignSel',req:1,full:1},{k:'date',l:'日期',t:'date',req:1},\n"
    "    {k:'spend',l:'当天消耗 (U)',t:'number',req:1},{k:'conversions',l:'当天转化数',t:'number'},\n"
    "    {k:'revenue',l:'当天转化价值 (U)',t:'number'},{k:'note',l:'备注(改了什么/发生了什么)',t:'textarea',full:1}\n"
    "  ],\n"
    "  payments:[\n    {k:'clientId',l:'客户',t:'clientSel',req:1,full:1},",
))
E.append((
    "const NEW_TITLES={clients:'新增客户',",
    "const NEW_TITLES={dailies:'记一天数据',clients:'新增客户',",
))
E.append((
    "const EDIT_TITLES={clients:'编辑客户',",
    "const EDIT_TITLES={dailies:'编辑每日数据',clients:'编辑客户',",
))

# ---- 5. 表单里要能选投放项目 ----
E.append((
    "  else if(f.t==='clientSel'){",
    "  else if(f.t==='campaignSel'){const opts=state.campaigns.map(c=>`<option value=\"${c.id}\" ${c.id===v?'selected':''}>${esc(c.name)}</option>`).join('');inner=`<select id=\"f_${f.k}\">${state.campaigns.length?opts:'<option value=\"\">先去「投放项目」建一条</option>'}</select>`;}\n"
    "  else if(f.t==='clientSel'){",
))

# ---- 6. 汇总 + 趋势图 + 视图 ----
DAILY_CODE = r"""
/* ============ 每日数据 ============ */
const DAY = 86400000;
function dstr(d){return new Date(d).toISOString().slice(0,10);}
function campName(id){const c=state.campaigns.find(x=>x.id===id);return c?c.name:'—';}
/* 某个项目的按天记录，按日期正序 */
function dailiesOf(cid){return state.dailies.filter(d=>d.campaignId===cid).sort((a,b)=>(a.date||'').localeCompare(b.date||''));}
/* 项目的累计数：有按天记录就用汇总的，没有就回落到手填的那个数 */
function rollup(c){
  const ds=dailiesOf(c.id);
  if(!ds.length) return {spent:Number(c.spent)||0,conversions:Number(c.conversions)||0,revenue:Number(c.revenue)||0,from:'手填'};
  return {
    spent:ds.reduce((s,d)=>s+(Number(d.spend)||0),0),
    conversions:ds.reduce((s,d)=>s+(Number(d.conversions)||0),0),
    revenue:ds.reduce((s,d)=>s+(Number(d.revenue)||0),0),
    from:ds.length+' 天汇总',
  };
}
/* 一段日期内的合计，用于周环比 */
function sumRange(from,to){
  const f=dstr(from),t=dstr(to);
  const rows=state.dailies.filter(d=>d.date>=f&&d.date<=t);
  return {spend:rows.reduce((s,d)=>s+(Number(d.spend)||0),0),
          conv:rows.reduce((s,d)=>s+(Number(d.conversions)||0),0),
          rev:rows.reduce((s,d)=>s+(Number(d.revenue)||0),0),days:rows.length};
}
function delta(now,prev){
  if(!prev) return '';
  const p=Math.round((now-prev)/prev*100);
  const cls=p>0?'p-green':(p<0?'p-red':'p-gray');
  return `<span class="pill ${cls}">${p>0?'+':''}${p}%</span>`;
}
/* 手画的折线图：不引任何图表库，就是一段 svg */
function spark(rows,key,color,h){
  h=h||54;
  const vals=rows.map(r=>Number(r[key])||0);
  if(vals.length<2) return `<div class="cell-sub" style="padding:8px 0">攒够两天数据才画得出趋势</div>`;
  const max=Math.max(...vals,1), w=Math.max(rows.length*26,200);
  const pts=vals.map((v,i)=>`${(i/(vals.length-1))*w},${h-(v/max)*(h-8)-4}`).join(' ');
  const last=vals[vals.length-1], first=vals[0];
  const area=`0,${h} ${pts} ${w},${h}`;
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:${h}px;display:block">
    <polygon points="${area}" fill="${color}" opacity=".12"/>
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>
    <circle cx="${w}" cy="${h-(last/max)*(h-8)-4}" r="3" fill="${color}"/>
  </svg>
  <div class="cell-sub" style="display:flex;justify-content:space-between;margin-top:2px">
    <span>${esc(rows[0].date||'')}</span><span>最高 ${fmt(Math.round(max))}</span><span>${esc(rows[rows.length-1].date||'')}</span>
  </div>`;
}
function viewDailies(){
  if(!state.campaigns.length) return emptyState('◷','先建投放项目','每日数据要挂在某条投放下面。先去「投放项目」建一条,再回来按天记数。','go(\'campaigns\')','去建投放项目');
  if(!state.dailies.length) return emptyState('◷','还没有按天数据','每天把各条投放的消耗和转化记一笔。趋势、周环比、月报、预算预警全靠这些行 —— 现在每条投放只有一个会被覆盖的累计数,看不出好坏变化。','openForm(\'dailies\')','+ 记一天数据');

  /* 最近 14 天全盘趋势 */
  const today=Date.now();
  const days=[];
  for(let i=13;i>=0;i--){
    const d=dstr(today-i*DAY);
    const rows=state.dailies.filter(x=>x.date===d);
    days.push({date:d,
      spend:rows.reduce((s,x)=>s+(Number(x.spend)||0),0),
      conv:rows.reduce((s,x)=>s+(Number(x.conversions)||0),0),
      rev:rows.reduce((s,x)=>s+(Number(x.revenue)||0),0)});
  }
  const trend=`<div class="prow" style="margin-bottom:16px">
    <div class="panel"><div class="panel-h"><h3>近 14 天消耗</h3></div><div style="padding:12px 16px">${spark(days,'spend','var(--accent)')}</div></div>
    <div class="panel"><div class="panel-h"><h3>近 14 天转化</h3></div><div style="padding:12px 16px">${spark(days,'conv','var(--blue)')}</div></div>
  </div>`;

  /* 周环比 */
  const tw=sumRange(today-6*DAY,today), lw=sumRange(today-13*DAY,today-7*DAY);
  const twRoas=tw.spend>0&&tw.rev>0?tw.rev/tw.spend:null, lwRoas=lw.spend>0&&lw.rev>0?lw.rev/lw.spend:null;
  const wow=`<div class="kpis">
    <div class="kpi"><div class="bar"></div><div class="lbl">本周消耗</div><div class="val">${fmt(Math.round(tw.spend))}<small>${CUR()}</small></div><div class="meta">上周 ${fmt(Math.round(lw.spend))} ${delta(tw.spend,lw.spend)}</div></div>
    <div class="kpi blue"><div class="bar"></div><div class="lbl">本周转化</div><div class="val">${fmt(tw.conv)}</div><div class="meta">上周 ${fmt(lw.conv)} ${delta(tw.conv,lw.conv)}</div></div>
    <div class="kpi"><div class="bar"></div><div class="lbl">本周 ROAS</div><div class="val">${twRoas==null?'—':roasTxt(twRoas)}</div><div class="meta">${lwRoas==null?'上周没数据':'上周 '+roasTxt(lwRoas)+' '+delta(twRoas||0,lwRoas||0)}</div></div>
    <div class="kpi amber"><div class="bar"></div><div class="lbl">记录天数</div><div class="val">${tw.days}<small>本周</small></div><div class="meta">${tw.days<7?'有漏记的天':'每天都记了 👍'}</div></div>
  </div>`;

  const rows=[...state.dailies].sort((a,b)=>(b.date||'').localeCompare(a.date||'')).slice(0,120);
  const body=rows.map(d=>{
    const sp=Number(d.spend)||0, cv=Number(d.conversions)||0, rv=Number(d.revenue)||0;
    const r=sp>0&&rv>0?rv/sp:null;
    return `<tr class="clk" onclick="openForm('dailies','${d.id}')">
      <td class="cell-sub">${esc(d.date||'')}</td>
      <td><div class="cell-main">${esc(campName(d.campaignId))}</div></td>
      <td class="num">${fmt(sp)} ${CUR()}</td>
      <td class="num">${cv||'—'}</td>
      <td class="num">${rv?fmt(rv)+' '+CUR():'—'}</td>
      <td class="num">${cv>0?fmt(Math.round(sp/cv*100)/100):'—'}</td>
      <td>${r==null?'—':`<span class="pill ${roasClass(r)}">${roasTxt(r)}</span>`}</td>
      <td class="cell-sub">${esc((d.note||'').slice(0,28))}</td></tr>`;
  }).join('');
  return trend+wow+`<div class="card"><div class="tbl-wrap"><table><thead><tr><th>日期</th><th>投放项目</th><th>消耗</th><th>转化</th><th>转化价值</th><th>CPA</th><th>ROAS</th><th>备注</th></tr></thead><tbody>${body}</tbody></table></div></div>`;
}
"""
E.append((
    "function viewTeam(){",
    DAILY_CODE + "\nfunction viewTeam(){",
))

# ---- 6b. loadAll 重建 state 时也要有 dailies，否则刷新即报错 ----
E.append((
    "const s={clients:[],campaigns:[],payments:[],packages:[],briefs:[],members:state.members||[],settings:{cur:'U'}};",
    "const s={clients:[],campaigns:[],payments:[],packages:[],briefs:[],dailies:[],members:state.members||[],settings:{cur:'U'}};",
))

# ---- 6c. 概览里「进行中的投放」小列表也用汇总值 ----
E.append((
    "const campRows=run.length?run.map(c=>{const pct=c.budget>0?Math.min(100,Math.round(c.spent/c.budget*100)):0;",
    "const campRows=run.length?run.map(c=>{const R=rollup(c);c={...c,spent:R.spent};"
    "const pct=c.budget>0?Math.min(100,Math.round(c.spent/c.budget*100)):0;",
))

# ---- 7. 投放项目列表改用汇总值 ----
E.append((
    "  const body=state.campaigns.map(c=>{const pct=c.budget>0?Math.min(100,Math.round(c.spent/c.budget*100)):0;",
    "  const body=state.campaigns.map(c=>{const R=rollup(c);c={...c,spent:R.spent,conversions:R.conversions,revenue:R.revenue};"
    "const pct=c.budget>0?Math.min(100,Math.round(c.spent/c.budget*100)):0;",
))
E.append((
    "<div class=\"num\" style=\"font-weight:600\">${fmt(c.spent)} ${CUR()} · ${pct}%</div>",
    "<div class=\"num\" style=\"font-weight:600\">${fmt(c.spent)} ${CUR()} · ${pct}%</div><div class=\"cell-sub\">${R.from}</div>",
))

# ---- 8. 概览也用汇总值 ----
E.append((
    "const mgBudget=run.reduce((s,c)=>s+(Number(c.budget)||0),0), mgSpent=run.reduce((s,c)=>s+(Number(c.spent)||0),0);",
    "const runR=run.map(c=>rollup(c));\n"
    "  const mgBudget=run.reduce((s,c)=>s+(Number(c.budget)||0),0), mgSpent=runR.reduce((s,r)=>s+r.spent,0);",
))
E.append((
    "  const mgConv=run.reduce((s,c)=>s+(Number(c.conversions)||0),0), mgRev=run.reduce((s,c)=>s+(Number(c.revenue)||0),0);",
    "  const mgConv=runR.reduce((s,r)=>s+r.conversions,0), mgRev=runR.reduce((s,r)=>s+r.revenue,0);",
))

missing = [i + 1 for i, (old, _) in enumerate(E) if s.count(old) != 1]
if missing:
    print("ABORTED, nothing changed. These anchors were not found exactly once:", missing)
    raise SystemExit(1)

out = s
for old, new in E:
    out = out.replace(old, new, 1)

if not os.path.exists(p + ".bak-daily"):
    shutil.copy2(p, p + ".bak-daily"); print("backup ->", p + ".bak-daily")
io.open(p, "w", encoding="utf-8").write(out)
print("每日数据模块 added: %d -> %d bytes" % (len(s.encode()), len(out.encode())))
