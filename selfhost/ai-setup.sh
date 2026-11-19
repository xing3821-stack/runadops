#!/bin/bash
# =====================================================================
# 打开控制台的 AI 生成功能
#
#   bash ai-setup.sh 'sk-ant-...'      # 带 key，装完直接验证
#   bash ai-setup.sh                   # 不带 key，只装代码（之后再填 key）
#
# 做这些事:
#   1. 更新后端代码,装 @anthropic-ai/sdk 和 zod
#   2. 把 key 写进 .env(权限 600),重启服务
#   3. 真发一次最小请求验证 key 能用(花费不到 1 分钱)
#   4. 给控制台的「投放配置」编辑框加「AI 生成物料」按钮
#   5. 把 nginx 的 /api/ 超时从 60s 调到 300s(生成要跑一分钟左右)
#
# 每步都先备份,失败就停下并打印还原方法。只动 /opt/runadops-api、
# /var/www/runadops/ 和 sites-available/runadops.com。
# =====================================================================
set -u

SRC="$(cd "$(dirname "$0")" && pwd)"
APP_DIR=${APP_DIR:-/opt/runadops-api}
WEB_DIR=${WEB_DIR:-/var/www/runadops}
NGINX_CONF=${NGINX_CONF:-/etc/nginx/sites-available/runadops.com}
DOMAIN=${DOMAIN:-runadops.com}
KEY="${1:-}"
# 端口以 .env 为准
PORT=$(sed -n "s/^PORT=//p" "${APP_DIR}/.env" 2>/dev/null | head -1)
PORT=${PORT:-8788}

GRN=$'\033[32m'; YEL=$'\033[33m'; RED=$'\033[31m'; OFF=$'\033[0m'
ok(){ echo "${GRN}  ✓${OFF} $*"; }
warn(){ echo "${YEL}  !${OFF} $*"; }
die(){ echo; echo "${RED}✗ 失败:$*${OFF}"; [ -n "${HINT:-}" ] && echo "还原:$HINT"; exit 1; }
step(){ echo; echo "${GRN}== $* ==${OFF}"; }
HINT=""

[ "$(id -u)" = "0" ] || die "要用 root 跑"
[ -d "$APP_DIR" ] || die "没有 $APP_DIR,先把自建后端装好(bash deploy.sh)"

step "1/5 更新后端代码"
for f in server.js ai.js patch-ai-ui.py nginx-ai-timeout.py; do
  [ -f "$SRC/$f" ] || die "源文件缺失:$SRC/$f"
  cp "$SRC/$f" "$APP_DIR/"
done
ok "文件已复制"
cd "$APP_DIR" || die "进不去 $APP_DIR"
npm install --omit=dev --no-fund --no-audit @anthropic-ai/sdk zod >/dev/null 2>&1 \
  || die "装依赖失败,手动跑一次看报错:cd $APP_DIR && npm install @anthropic-ai/sdk zod"
ok "@anthropic-ai/sdk 和 zod 装好了"

step "2/5 写入 API key"
if [ -n "$KEY" ]; then
  cp .env .env.bak-ai 2>/dev/null
  sed -i '/^ANTHROPIC_API_KEY=/d' .env
  printf 'ANTHROPIC_API_KEY=%s\n' "$KEY" >> .env
  chmod 600 .env
  ok "已写进 $APP_DIR/.env(权限 600),key 长度 ${#KEY}"
  if [ "${#KEY}" -lt 80 ]; then
    warn "这个 key 看着偏短(正常是 100 出头),可能粘贴时被截断了 —— 下一步会验证"
  fi
else
  if grep -q '^ANTHROPIC_API_KEY=' .env 2>/dev/null; then
    ok "沿用 .env 里已有的 key"
  else
    warn "没给 key,也没有现成的。AI 按钮会装上,但点了会提示没配 key"
    warn "以后补:在 $APP_DIR/.env 里加一行 ANTHROPIC_API_KEY=sk-ant-...,然后 pm2 restart runadops-api"
  fi
fi

pm2 restart runadops-api >/dev/null 2>&1 || die "重启后端失败,看 pm2 logs runadops-api"
sleep 2
curl -sS --max-time 10 "http://127.0.0.1:$PORT/api/health" | grep -q '"ok":true' || die "后端没起来,看 pm2 logs runadops-api"
ok "后端已重启"

step "3/5 验证 key"
if grep -q '^ANTHROPIC_API_KEY=' .env 2>/dev/null; then
  if node server.js aicheck; then
    ok "key 可用"
  else
    warn "key 验证没过(上面有原因)。其他都装好了,改完 .env 再跑:cd $APP_DIR && node server.js aicheck"
  fi
else
  warn "没有 key,跳过验证"
fi

step "4/5 给控制台加 AI 按钮"
cd "$WEB_DIR" || die "进不去 $WEB_DIR"
python3 "$APP_DIR/patch-ai-ui.py" index.html || die "改 index.html 失败(没动过文件)"
HINT="cd $WEB_DIR && cp index.html.bak-aiui index.html"
ok "按钮已加上"

step "5/5 调大 nginx 的 /api/ 超时"
OUT=$(python3 "$APP_DIR/nginx-ai-timeout.py" "$NGINX_CONF" 300) || die "改 nginx 失败:$OUT"
echo "$OUT" | sed 's/^/  /'
NGX_BAK=$(echo "$OUT" | sed -n 's/^BACKUP=//p')
if [ -n "$NGX_BAK" ]; then
  if ! nginx -t >/dev/null 2>&1; then
    cp "$NGX_BAK" "$NGINX_CONF"
    nginx -t 2>&1 | sed 's/^/  /'
    die "nginx -t 没过,已自动还原,网站没受影响"
  fi
  systemctl reload nginx || die "reload nginx 失败"
  ok "nginx 已重载"
fi

step "自检"
curl -sS --max-time 15 "https://$DOMAIN/api/health" | grep -q '"ok":true' && ok "公网接口正常" || warn "公网接口没通,等几秒再试"
curl -sS --max-time 15 "https://$DOMAIN/" | grep -q 'aiGenerate' && ok "页面里有 AI 按钮了" || warn "页面里没看到,可能有缓存,Ctrl+F5"

cat <<EOF

${GRN}================ 装完了 ================${OFF}

去 https://$DOMAIN ,Ctrl+F5 强刷,进「投放配置」点开任意一份,
编辑框底部会多一个「✨ AI 生成物料」按钮。

点它会先问你"这个项目卖什么",填一句话,然后等半分钟到一分钟,
文案 / 欢迎语 / 兴趣词 / 素材方向 / 口播脚本会自动填进表单。
**检查后再点保存** —— 不点保存不会写进数据库。

每次大约 \$0.05,生成完界面上会显示这次花了多少。

想换模型:在 $APP_DIR/.env 里加 AI_MODEL=claude-sonnet-5-5 (便宜些),
然后 pm2 restart runadops-api。

撤掉 AI 按钮:cd $WEB_DIR && cp index.html.bak-aiui index.html
EOF
[ -n "${NGX_BAK:-}" ] && echo "还原 nginx 超时:cp $NGX_BAK $NGINX_CONF && systemctl reload nginx"
echo
