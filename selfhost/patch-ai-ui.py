#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Add the "AI generate" button to the brief editor in the console.
# ASCII-only on purpose except for the UI strings it injects.
#
#   cd /var/www/runadops && python3 patch-ai-ui.py index.html
#
# Four edits:
#   1. briefs schema: add a "script" (voiceover script) textarea field
#   2. modal footer: add the AI button + a status line
#   3. openForm: show that button only for briefs
#   4. add the aiGenerate() function that calls POST /api/ai/brief
#
# Aborts without touching anything if an anchor is missing.
# Keeps a .bak-aiui (never overwrites an existing one). Safe to run twice.
import io, os, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

if "aiGenerate" in s:
    print("Already patched, nothing to do."); raise SystemExit

EDITS = []

# 1. schema: add the voiceover-script field
EDITS.append((
    "{k:'creative',l:'素材方向(AI + 实拍)',t:'textarea',full:1},{k:'status',l:'状态',t:'select',opt:['草稿','在投','暂停']},",
    "{k:'creative',l:'素材方向(AI + 实拍)',t:'textarea',full:1},"
    "{k:'script',l:'口播脚本(真人视频用)',t:'textarea',full:1},"
    "{k:'status',l:'状态',t:'select',opt:['草稿','在投','暂停']},",
))

# 2. modal footer: the button lives next to 删除
EDITS.append((
    '<div class="modal-f"><button class="del" id="delBtn" onclick="deleteCurrent()" style="display:none">删除</button><div class="spacer"></div>',
    '<div class="modal-f"><button class="del" id="delBtn" onclick="deleteCurrent()" style="display:none">删除</button>'
    '<button class="btn ghost" id="aiBtn" onclick="aiGenerate()" style="display:none">✨ AI 生成物料</button>'
    '<span id="aiMsg" style="font-size:12px;color:var(--muted2);margin-left:10px;max-width:260px"></span>'
    '<div class="spacer"></div>',
))

# 3. openForm: only briefs get the button
EDITS.append((
    "  $('delBtn').style.display=(id&&isAdmin())?'block':'none';",
    "  $('delBtn').style.display=(id&&isAdmin())?'block':'none';\n"
    "  $('aiBtn').style.display=(coll==='briefs')?'inline-flex':'none';\n"
    "  $('aiMsg').textContent='';",
))

# 4. the generator itself
AI_FN = """async function aiGenerate(){
  const btn=$('aiBtn'), msg=$('aiMsg');
  const fields={};
  SCHEMAS.briefs.forEach(f=>{const e=$('f_'+f.k); if(e) fields[f.k]=e.value;});
  if(!fields.project){msg.textContent='先填「项目 / 站点」';return;}
  const product=prompt('这个项目卖什么 / 做什么服务?一两句话说清楚,AI 按这个写文案:', fields.note||'');
  if(product===null) return;
  btn.disabled=true; const old=btn.textContent; btn.textContent='生成中…';
  msg.textContent='正在生成,大概半分钟到一分钟,别关窗口';
  try{
    const r=await fetch('/api/ai/brief',{
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({briefId:editing.id||undefined, fields, product})
    });
    const j=await r.json();
    if(!r.ok){ msg.textContent='失败:'+(j.error||('HTTP '+r.status)); return; }
    ['copy','welcome','interests','creative','script'].forEach(k=>{
      const e=$('f_'+k); if(e&&j.fields[k]) e.value=j.fields[k];
    });
    msg.textContent='生成好了,检查后点保存(本次约 $'+j.usage.cost_usd+')';
  }catch(e){
    msg.textContent='出错:'+e.message;
  }finally{
    btn.disabled=false; btn.textContent=old;
  }
}
"""
EDITS.append((
    "function closeModal(){$('overlay').classList.remove('show');editing={coll:null,id:null};}",
    AI_FN + "function closeModal(){$('overlay').classList.remove('show');editing={coll:null,id:null};}",
))

missing = [i + 1 for i, (old, _) in enumerate(EDITS) if s.count(old) != 1]
if missing:
    print("ABORTED, nothing changed. These anchors were not found exactly once:", missing)
    raise SystemExit(1)

out = s
for old, new in EDITS:
    out = out.replace(old, new, 1)

if not os.path.exists(p + ".bak-aiui"):
    shutil.copy2(p, p + ".bak-aiui"); print("backup ->", p + ".bak-aiui")
io.open(p, "w", encoding="utf-8").write(out)
print("AI button added: %d -> %d bytes" % (len(s.encode()), len(out.encode())))
