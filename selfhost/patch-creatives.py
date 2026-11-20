#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# A creative library, with per-creative numbers and fatigue detection.
#
#   cd /var/www/runadops && python3 patch-creatives.py index.html
#
# The point: a daily row can now carry a creative, so每条素材的消耗/转化/ROAS
# come out of the data you already record — no platform API needed. On top of
# that the console判断衰减: 近 3 天 vs 之前的表现掉得太多就提示该换。
#
# Needs patch-daily.py first.
# Aborts without touching anything if an anchor is missing. Keeps a .bak-creatives.
import io, os, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

if "viewCreatives" in s:
    print("Already patched, nothing to do."); raise SystemExit
if "viewDailies" not in s:
    print("ABORTED: 先跑 patch-daily.py(素材表现要从按天数据算)")
    print("  python3 patch-daily.py " + p)
    raise SystemExit(1)

E = []

# 1. 类型表 + state
E.append((
    "const COLL_TYPE={clients:'client',campaigns:'campaign',payments:'payment',packages:'package',briefs:'brief',dailies:'daily'};\n"
    "const TYPE_COLL={client:'clients',campaign:'campaigns',payment:'payments',package:'packages',brief:'briefs',daily:'dailies'};",

    "const COLL_TYPE={clients:'client',campaigns:'campaign',payments:'payment',packages:'package',briefs:'brief',dailies:'daily',creatives:'creative'};\n"
    "const TYPE_COLL={client:'clients',campaign:'campaigns',payment:'payments',package:'packages',brief:'briefs',daily:'dailies',creative:'creatives'};",
))
E.append((
    "let state={clients:[],campaigns:[],payments:[],packages:[],briefs:[],dailies:[],members:[],settings:{cur:'U'}};",
    "let state={clients:[],campaigns:[],payments:[],packages:[],briefs:[],dailies:[],creatives:[],members:[],settings:{cur:'U'}};",
))
E.append((
    "const s={clients:[],campaigns:[],payments:[],packages:[],briefs:[],dailies:[],members:state.members||[],settings:{cur:'U'}};",
    "const s={clients:[],campaigns:[],payments:[],packages:[],briefs:[],dailies:[],creatives:[],members:state.members||[],settings:{cur:'U'}};",
))
E.append((
    "  ['clients','campaigns','payments','packages','briefs','dailies','members'].forEach(k=>{if(!Array.isArray(state[k]))state[k]=[];});",
    "  ['clients','campaigns','payments','packages','briefs','dailies','creatives','members'].forEach(k=>{if(!Array.isArray(state[k]))state[k]=[];});",
))

# 2. 导航 / 标题 / 按钮 / 视图表
E.append((
    "  {id:'dailies',name:'每日数据',ic:'◷',coll:'dailies'},\n",
    "  {id:'creatives',name:'素材库',ic:'✎',coll:'creatives'},\n"
    "  {id:'dailies',name:'每日数据',ic:'◷',coll:'dailies'},\n",
))
E.append((
    "dailies:['每日数据','按天记消耗和转化 —— 趋势、周环比、月报都靠它'],",
    "dailies:['每日数据','按天记消耗和转化 —— 趋势、周环比、月报都靠它'],"
    "creatives:['素材库','跑过哪些素材、哪条还在赚钱、哪条该换了'],",
))
E.append((
    "packages:'+ 新增套餐',dailies:'+ 记一天数据'};",
    "packages:'+ 新增套餐',dailies:'+ 记一天数据',creatives:'+ 新增素材'};",
))
E.append((
    "dailies:viewDailies,",
    "dailies:viewDailies,creatives:viewCreatives,",
))

# 3. 表单字段:素材本身,以及每日数据可以挂到素材上
E.append((
    "  dailies:[\n"
    "    {k:'campaignId',l:'投放项目',t:'campaignSel',req:1,full:1},{k:'date',l:'日期',t:'date',req:1},",

    "  creatives:[\n"
    "    {k:'name',l:'素材名',t:'text',req:1,full:1},\n"
    "    {k:'type',l:'类型',t:'select',opt:CREATIVE_TYPES},{k:'lang',l:'语言',t:'text'},\n"
    "    {k:'campaignId',l:'主要用在',t:'campaignSel',full:1},\n"
    "    {k:'url',l:'文件链接 / 预览地址',t:'text',full:1},\n"
    "    {k:'launched',l:'上线日期',t:'date'},{k:'status',l:'状态',t:'select',opt:CREATIVE_STATUS.map(x=>x[0])},\n"
    "    {k:'hook',l:'钩子 / 卖点',t:'textarea',full:1},{k:'note',l:'备注',t:'textarea',full:1}\n"
    "  ],\n"
    "  dailies:[\n"
    "    {k:'campaignId',l:'投放项目',t:'campaignSel',req:1,full:1},"
    "{k:'creativeId',l:'素材(可不填)',t:'creativeSel',full:1},{k:'date',l:'日期',t:'date',req:1},",
))
E.append((
    "const NEW_TITLES={dailies:'记一天数据',",
    "const NEW_TITLES={creatives:'新增素材',dailies:'记一天数据',",
))
E.append((
    "const EDIT_TITLES={dailies:'编辑每日数据',",
    "const EDIT_TITLES={creatives:'编辑素材',dailies:'编辑每日数据',",
))

# 4. 表单里要能选素材
E.append((
    "  else if(f.t==='campaignSel'){",
    "  else if(f.t==='creativeSel'){const opts=state.creatives.map(c=>`<option value=\"${c.id}\" ${c.id===v?'selected':''}>${esc(c.name)}</option>`).join('');"
    "inner=`<select id=\"f_${f.k}\"><option value=\"\">—(不挂素材)</option>${opts}</select>`;}\n"
    "  else if(f.t==='campaignSel'){",
))

# 5. 常量 + 表现计算 + 视图
CODE = r"""
/* ============ 素材库 ============ */
const CREATIVE_TYPES=['竖版视频','横版视频','AI 口播','实拍','单图','轮播','图文'];
const CREATIVE_STATUS=[['在投','p-green'],['测试中','p-blue'],['已衰减','p-amber'],['已下架','p-gray']];

/* 一条素材的累计表现:从挂了这条素材的每日数据里加出来 */
function creativePerf(cr){
  const ds=state.dailies.filter(d=>d.creativeId===cr.id).sort((a,b)=>(a.date||'').localeCompare(b.date||''));
  const sum=rows=>({
    spend:rows.reduce((s,d)=>s+(Number(d.spend)||0),0),
    conv:rows.reduce((s,d)=>s+(Number(d.conversions)||0),0),
    rev:rows.reduce((s,d)=>s+(Number(d.revenue)||0),0),
  });
  const all=sum(ds);
  const today=Date.now();
  const recent=sum(ds.filter(d=>d.date>=dstr(today-2*DAY)));   /* 近 3 天 */
  const before=sum(ds.filter(d=>d.date<dstr(today-2*DAY)));    /* 更早 */
  const roasOf=x=>x.spend>0&&x.rev>0?x.rev/x.spend:null;
  const cpaOf=x=>x.conv>0?x.spend/x.conv:null;
  return {days:ds.length,first:ds[0]?ds[0].date:null,last:ds[ds.length-1]?ds[ds.length-1].date:null,
          ...all,roas:roasOf(all),cpa:cpaOf(all),
          recent:{...recent,roas:roasOf(recent),cpa:cpaOf(recent)},
          before:{...before,roas:roasOf(before),cpa:cpaOf(before)}};
}
/* 衰减判断:近 3 天比之前明显变差就提示该换。
   数据太少不判 —— 宁可不说，也别乱报。 */
function fatigue(p){
  if(p.days<5||p.recent.spend<=0||p.before.spend<=0) return null;
  if(p.before.roas!=null&&p.recent.roas!=null){
    const drop=(p.before.roas-p.recent.roas)/p.before.roas;
    if(drop>=0.3) return {level:drop>=0.5?'red':'amber',
      text:`ROAS 从 ${roasTxt(p.before.roas)} 掉到 ${roasTxt(p.recent.roas)}(-${Math.round(drop*100)}%)`};
  }
  if(p.before.cpa!=null&&p.recent.cpa!=null){
    const up=(p.recent.cpa-p.before.cpa)/p.before.cpa;
    if(up>=0.5) return {level:up>=1?'red':'amber',
      text:`CPA 从 ${fmt(Math.round(p.before.cpa))} 涨到 ${fmt(Math.round(p.recent.cpa))}(+${Math.round(up*100)}%)`};
  }
  return null;
}
function viewCreatives(){
  const note=`<div class="section-head section-note">把每条跑过的素材记在这里,<b>记每日数据时挂上对应素材</b>,
    消耗/转化/ROAS 就按素材自动算出来。跑够 5 天后,近 3 天明显变差的会自动标「该换了」。</div>`;
  if(!state.creatives.length) return note+emptyState('✎','还没有素材','素材是广告里最值钱也最容易忘的东西 —— 跑过什么、哪条好用,过两个月就想不起来了。先把在投的几条录进来。','openForm(\'creatives\')','+ 新增素材');

  const rows=state.creatives.map(cr=>{
    const p=creativePerf(cr), f=fatigue(p);
    const st=CREATIVE_STATUS.find(x=>x[0]===cr.status);
    return {cr,p,f,html:`<tr class="clk" onclick="openForm('creatives','${cr.id}')">
      <td><div class="cell-main">${esc(cr.name)}</div><div class="cell-sub">${esc(cr.type||'—')}${cr.lang?' · '+esc(cr.lang):''}${cr.campaignId?' · '+esc(campName(cr.campaignId)):''}</div></td>
      <td>${f?`<span class="pill ${f.level==='red'?'p-red':'p-amber'}">该换了</span>`:`<span class="pill ${st?st[1]:'p-gray'}">${esc(cr.status||'—')}</span>`}
          ${f?`<div class="cell-sub" style="margin-top:4px">${esc(f.text)}</div>`:''}</td>
      <td class="num">${p.days?fmt(Math.round(p.spend))+' '+CUR():'<span class="cell-sub">没挂数据</span>'}</td>
      <td class="num">${p.conv||'—'}</td>
      <td class="num">${p.cpa==null?'—':fmt(Math.round(p.cpa*100)/100)}</td>
      <td>${p.roas==null?'—':`<span class="pill ${roasClass(p.roas)}">${roasTxt(p.roas)}</span>`}</td>
      <td class="cell-sub">${p.days?p.days+' 天 · ${}'.replace('${}',esc(p.first||''))+' 起':esc(cr.launched||'')}</td>
    </tr>`};
  });
  /* 花得多的排前面，没数据的垫底 */
  rows.sort((a,b)=>b.p.spend-a.p.spend);
  const tired=rows.filter(r=>r.f).length;
  const head=tired?`<div class="section-note" style="border-left-color:var(--amber)">有 <b>${tired}</b> 条素材近 3 天明显变差,建议换掉或减预算。</div>`:'';
  return note+head+`<div class="card"><div class="tbl-wrap"><table><thead><tr>
    <th>素材</th><th>状态</th><th>消耗</th><th>转化</th><th>CPA</th><th>ROAS</th><th>跑了多久</th>
    </tr></thead><tbody>${rows.map(r=>r.html).join('')}</tbody></table></div></div>`;
}
"""
E.append(("function viewTeam(){", CODE + "\nfunction viewTeam(){"))

missing = [i + 1 for i, (old, _) in enumerate(E) if s.count(old) != 1]
if missing:
    print("ABORTED, nothing changed. These anchors were not found exactly once:", missing)
    raise SystemExit(1)

out = s
for old, new in E:
    out = out.replace(old, new, 1)

if not os.path.exists(p + ".bak-creatives"):
    shutil.copy2(p, p + ".bak-creatives"); print("backup ->", p + ".bak-creatives")
io.open(p, "w", encoding="utf-8").write(out)
print("素材库 added: %d -> %d bytes" % (len(s.encode()), len(out.encode())))
