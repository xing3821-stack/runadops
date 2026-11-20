#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# More platforms, and an account ledger: which client holds which BM / ad account
# / page / pixel / WhatsApp number, who owns it, and what state it is in.
#
#   cd /var/www/runadops && python3 patch-accounts.py index.html
#
# It records; it does not supply accounts. 受限 / 已封 / 待验证 的会进预警。
#
# Needs patch-alerts.py first (so account states can raise alerts).
# Aborts without touching anything if an anchor is missing. Keeps a .bak-accounts.
import io, os, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

if "viewAccounts" in s:
    print("Already patched, nothing to do."); raise SystemExit
if "function alerts(" not in s:
    print("ABORTED: 先跑 patch-alerts.py(账号状态要能进预警)")
    print("  python3 patch-alerts.py " + p)
    raise SystemExit(1)

E = []

# 1. 平台补全
E.append((
    "const PLATFORMS=['Facebook','Instagram','TikTok','Google'];",
    "const PLATFORMS=['Facebook','Instagram','TikTok','小红书','Google','YouTube','Snapchat','Kwai','X (Twitter)','WhatsApp'];",
))

# 2. 类型表 / state / 导航 / 标题 / 按钮 / 视图表
E.append((
    "const COLL_TYPE={clients:'client',campaigns:'campaign',payments:'payment',packages:'package',briefs:'brief',dailies:'daily',creatives:'creative'};\n"
    "const TYPE_COLL={client:'clients',campaign:'campaigns',payment:'payments',package:'packages',brief:'briefs',daily:'dailies',creative:'creatives'};",

    "const COLL_TYPE={clients:'client',campaigns:'campaign',payments:'payment',packages:'package',briefs:'brief',dailies:'daily',creatives:'creative',accounts:'account'};\n"
    "const TYPE_COLL={client:'clients',campaign:'campaigns',payment:'payments',package:'packages',brief:'briefs',daily:'dailies',creative:'creatives',account:'accounts'};",
))
E.append((
    "let state={clients:[],campaigns:[],payments:[],packages:[],briefs:[],dailies:[],creatives:[],members:[],settings:{cur:'U'}};",
    "let state={clients:[],campaigns:[],payments:[],packages:[],briefs:[],dailies:[],creatives:[],accounts:[],members:[],settings:{cur:'U'}};",
))
E.append((
    "const s={clients:[],campaigns:[],payments:[],packages:[],briefs:[],dailies:[],creatives:[],members:state.members||[],settings:{cur:'U'}};",
    "const s={clients:[],campaigns:[],payments:[],packages:[],briefs:[],dailies:[],creatives:[],accounts:[],members:state.members||[],settings:{cur:'U'}};",
))
E.append((
    "  ['clients','campaigns','payments','packages','briefs','dailies','creatives','members'].forEach(k=>{if(!Array.isArray(state[k]))state[k]=[];});",
    "  ['clients','campaigns','payments','packages','briefs','dailies','creatives','accounts','members'].forEach(k=>{if(!Array.isArray(state[k]))state[k]=[];});",
))
E.append((
    "  {id:'clients',name:'客户',ic:'◆',coll:'clients'},\n",
    "  {id:'clients',name:'客户',ic:'◆',coll:'clients'},\n"
    "  {id:'accounts',name:'账号台账',ic:'⛁',coll:'accounts'},\n",
))
E.append((
    "clients:['客户','管好每一个接单客户'],",
    "clients:['客户','管好每一个接单客户'],"
    "accounts:['账号台账','哪个客户有哪些 BM、广告户、主页、验证到哪一步'],",
))
E.append((
    "const addLabels={clients:'+ 新增客户',",
    "const addLabels={accounts:'+ 登记账号',clients:'+ 新增客户',",
))
E.append((
    "const V={overview:viewOverview,clients:viewClients,",
    "const V={overview:viewOverview,accounts:viewAccounts,clients:viewClients,",
))

# 3. 表单
E.append((
    "  clients:[\n    {k:'name',l:'客户名 / 公司',t:'text',req:1,full:1},",
    "  accounts:[\n"
    "    {k:'clientId',l:'归属客户',t:'clientSel',req:1,full:1},\n"
    "    {k:'platform',l:'平台',t:'select',opt:PLATFORMS},{k:'kind',l:'类型',t:'select',opt:ACCOUNT_KINDS},\n"
    "    {k:'ident',l:'账号 ID / 名称',t:'text',req:1,full:1},\n"
    "    {k:'owner',l:'归属',t:'select',opt:ACCOUNT_OWNERS},{k:'status',l:'状态',t:'select',opt:ACCOUNT_STATUS.map(x=>x[0])},\n"
    "    {k:'verified',l:'验证通过日期',t:'date'},{k:'access',l:'我方权限',t:'select',opt:['合作伙伴授权','被添加为成员','无','未知']},\n"
    "    {k:'note',l:'备注(谁办的、绑了什么卡、到期提醒)',t:'textarea',full:1}\n"
    "  ],\n"
    "  clients:[\n    {k:'name',l:'客户名 / 公司',t:'text',req:1,full:1},",
))
E.append((
    "const NEW_TITLES={creatives:'新增素材',",
    "const NEW_TITLES={accounts:'登记账号',creatives:'新增素材',",
))
E.append((
    "const EDIT_TITLES={creatives:'编辑素材',",
    "const EDIT_TITLES={accounts:'编辑账号',creatives:'编辑素材',",
))

# 4. 常量 + 视图
CODE = r"""
/* ============ 账号台账 ============ */
const ACCOUNT_KINDS=['企业管理平台 BM','广告账户','公共主页 Page','Pixel / 转化 API','WhatsApp 商业号','支付方式','商品目录','其他'];
const ACCOUNT_OWNERS=['客户自有','我方持有'];
const ACCOUNT_STATUS=[['正常','p-green'],['待验证','p-amber'],['受限','p-amber'],['已封','p-red'],['已停用','p-gray']];

function viewAccounts(){
  const note=`<div class="section-note">记清楚每个客户手上有哪些资产、在谁名下、验证到哪一步。
    <b>这里只做台账,不提供账号</b> —— 广告户建在客户自己的 BM 里,我们拿合作伙伴授权。
    状态标成「受限 / 已封 / 待验证」的会出现在概览的预警里。</div>`;
  if(!state.accounts.length) return note+emptyState('⛁','还没登记账号','新客户上线时把 BM、广告户、主页、Pixel、WhatsApp 号逐条登记,以后查授权、查到期、交接都看这一页。','openForm(\'accounts\')','+ 登记账号');

  /* 按客户分组，一个客户一张卡 */
  const byClient={};
  state.accounts.forEach(a=>{(byClient[a.clientId]=byClient[a.clientId]||[]).push(a);});
  const cards=Object.keys(byClient).map(cid=>{
    const list=byClient[cid];
    const bad=list.filter(a=>a.status==='已封'||a.status==='受限'||a.status==='待验证').length;
    const rows=list.map(a=>{
      const st=ACCOUNT_STATUS.find(x=>x[0]===a.status);
      return `<div class="mini" onclick="openForm('accounts','${a.id}')" style="cursor:pointer">
        <div style="flex:1">
          <div class="nm">${esc(a.ident||'(没填 ID)')}</div>
          <div class="sb">${esc(a.platform||'—')} · ${esc(a.kind||'—')} · ${esc(a.owner||'归属未填')}${a.access?' · '+esc(a.access):''}</div>
        </div>
        <div class="rt">
          <span class="pill ${st?st[1]:'p-gray'}">${esc(a.status||'—')}</span>
          ${a.verified?`<div class="sb">验证 ${esc(a.verified)}</div>`:''}
        </div></div>`;
    }).join('');
    return `<div class="panel" style="margin-bottom:14px${bad?';border-color:var(--amber)':''}">
      <div class="panel-h"><h3>${esc(clientName(cid))}</h3><div class="spacer"></div>
        <span class="cell-sub">${list.length} 项资产${bad?` · ${bad} 项要处理`:''}</span></div>
      <div class="panel-b">${rows}</div></div>`;
  }).join('');
  return note+cards;
}
"""
E.append(("function viewTeam(){", CODE + "\nfunction viewTeam(){"))

# 5. 账号状态进预警
E.append((
    "  /* 逾期未收 */",
    "  /* 账号状态:封了、受限、迟迟没验证 */\n"
    "  state.accounts.forEach(a=>{\n"
    "    if(a.status==='已封'){\n"
    "      out.push({level:'red',tag:'账号',text:`${clientName(a.clientId)} 的${a.kind||'账号'} ${a.ident||''} 已封`,\n"
    "        go:`openForm('accounts','${a.id}')`});\n"
    "    } else if(a.status==='受限'){\n"
    "      out.push({level:'red',tag:'账号',text:`${clientName(a.clientId)} 的${a.kind||'账号'} ${a.ident||''} 受限中`,\n"
    "        go:`openForm('accounts','${a.id}')`});\n"
    "    } else if(a.status==='待验证'){\n"
    "      out.push({level:'amber',tag:'账号',text:`${clientName(a.clientId)} 的${a.kind||'账号'} ${a.ident||''} 还没验证通过`,\n"
    "        go:`openForm('accounts','${a.id}')`});\n"
    "    }\n"
    "  });\n\n"
    "  /* 逾期未收 */",
))

missing = [i + 1 for i, (old, _) in enumerate(E) if s.count(old) != 1]
if missing:
    print("ABORTED, nothing changed. These anchors were not found exactly once:", missing)
    raise SystemExit(1)

out = s
for old, new in E:
    out = out.replace(old, new, 1)

if not os.path.exists(p + ".bak-accounts"):
    shutil.copy2(p, p + ".bak-accounts"); print("backup ->", p + ".bak-accounts")
io.open(p, "w", encoding="utf-8").write(out)
print("账号台账 + 平台补全 added: %d -> %d bytes" % (len(s.encode()), len(out.encode())))
