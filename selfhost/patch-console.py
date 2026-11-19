#!/usr/bin/env python3
# Switch the console from Supabase to the self-hosted /api backend.
# ASCII-only: meant to be pasted into an SSH session from a Windows console.
#
#   cd /var/www/runadops && python3 patch-console.py index.html
#
# What it changes (2 spots):
#   1. the supabase-js <script> tag(s) -> local shim.js
#   2. nothing else; the shim speaks the same API the console already calls
#
# Aborts without touching anything if it cannot find what it expects.
# Keeps a .bak-supabase (never overwrites an existing one). Safe to run twice.
import io, os, re, shutil, sys

p = sys.argv[1] if len(sys.argv) > 1 else "index.html"
s = io.open(p, encoding="utf-8").read()

if 'src="shim.js"' in s:
    print("Already switched to the self-hosted backend, nothing to do."); raise SystemExit

# all supabase-js script tags (pinned or not), plus the unpkg fallback line
pat_cdn = re.compile(
    r'[ \t]*<script[^>]*src="https://(?:cdn\.jsdelivr\.net|unpkg\.com)/npm/@supabase/supabase-js[^"]*"[^>]*></script>\n?'
    r'|[ \t]*<script>window\.supabase\|\|document\.write\([^\n]*\n?')

n_cdn = len(pat_cdn.findall(s))
if not n_cdn:
    print("ABORTED: no supabase-js script tag found. Is this the right file?"); raise SystemExit(1)

s2 = pat_cdn.sub("", s)
# insert the shim right before config.js
m = re.search(r'[ \t]*<script src="config\.js"></script>', s2)
if not m:
    print("ABORTED: config.js script tag not found."); raise SystemExit(1)
s2 = s2[:m.start()] + '<script src="shim.js"></script>\n' + s2[m.start():]

if not os.path.exists(p + ".bak-supabase"):
    shutil.copy2(p, p + ".bak-supabase"); print("backup ->", p + ".bak-supabase")
else:
    print("backup already exists:", p + ".bak-supabase")
io.open(p, "w", encoding="utf-8").write(s2)
print("removed %d supabase-js script line(s), added shim.js" % n_cdn)
print("patched: %d -> %d bytes" % (len(s.encode()), len(s2.encode())))
