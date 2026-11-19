#!/usr/bin/env python3
# Patch the live runadops console in place. ASCII-only on purpose: this file is
# meant to be pasted into an SSH session from a Windows console.
#
#   cd /var/www/runadops && python3 patch-live.py index.html
#
# Three fixes (full explanation in deployed/README.md):
#   1. backup filename -> ASCII  (Chromium drops non-ASCII download filenames)
#   2. records query pagination  (PostgREST caps at 1000 rows, silently)
#   3. pin supabase-js 2.119.1 + unpkg fallback  (blank page if jsdelivr is down)
#
# Aborts without touching anything if the file is not the expected version.
# Keeps a .bak (never overwrites an existing one). Safe to run twice.
import io, os, re, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

if "runadops-backup-" in s and ".range(_from" in s and "2.119.1" in s:
    print("Already patched, nothing to do."); raise SystemExit

subs = [
  ("backup filename -> ascii",
   r"a\.download='[^']*'\+new Date",
   "a.download='runadops-backup-'+new Date"),
  ("records pagination",
   r"const \{data,error\}=await supa\.from\('records'\)\.select\('\*'\);",
   "let data=[],error=null,_from=0;for(;;){const _r=await supa.from('records').select('*').range(_from,_from+999);if(_r.error){error=_r.error;break;}const _p=_r.data||[];data=data.concat(_p);if(_p.length<1000)break;_from+=1000;}"),
  ("pin supabase-js + unpkg fallback",
   r'<script src="https://cdn\.jsdelivr\.net/npm/@supabase/supabase-js@2"></script>',
   '<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.119.1/dist/umd/supabase.js"></script>\n'
   '<script>window.supabase||document.write(\'<script src="https://unpkg.com/@supabase/supabase-js@2.119.1/dist/umd/supabase.js"><\\/script>\');</script>'),
]

out, bad = s, []
for name, pat, rep in subs:
    out, n = re.subn(pat, rep, out, count=1)
    if not n: bad.append(name)
if bad:
    print("ABORTED, nothing changed. Not found:")
    for b in bad: print("  x", b)
    raise SystemExit(1)

if not os.path.exists(p + ".bak"):
    shutil.copy2(p, p + ".bak"); print("backup ->", p + ".bak")
else:
    print("backup already exists:", p + ".bak")
io.open(p, "w", encoding="utf-8").write(out)
print("patched: %d -> %d bytes" % (len(s.encode()), len(out.encode())))
