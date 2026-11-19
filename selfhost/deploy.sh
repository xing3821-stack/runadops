#!/bin/bash
# =====================================================================
# runadops 操盘控制台 · 一键切到自建后端
#
#   bash deploy.sh
#
# 它会做这些事(每一步都先备份、失败就停下并告诉你怎么还原):
#   1. 检查环境(mysql / node / pm2 / nginx / 网站目录)
#   2. 把后端装到 /opt/runadops-api 并用 pm2 拉起
#   3. 往 runadops.com 的 nginx 配置里加 /api/ 转发(nginx -t 不过就自动还原)
#   4. 把前端从 Supabase 切到 /api
#   5. 自检:本地接口、公网接口、页面
#
# 只动这几处:/opt/runadops-api、/var/www/runadops/、
# /etc/nginx/sites-available/runadops.com。服务器上其他站点一概不碰。
# =====================================================================
set -u

SRC="$(cd "$(dirname "$0")" && pwd)"
# 这几个可以用环境变量覆盖，方便在别处先演练一遍
APP_DIR=${APP_DIR:-/opt/runadops-api}
WEB_DIR=${WEB_DIR:-/var/www/runadops}
NGINX_CONF=${NGINX_CONF:-/etc/nginx/sites-available/runadops.com}
PORT=${PORT:-8788}
DOMAIN=${DOMAIN:-runadops.com}

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; OFF=$'\033[0m'
ok()   { echo "${GRN}  ✓${OFF} $*"; }
warn() { echo "${YEL}  !${OFF} $*"; }
die()  { echo; echo "${RED}✗ 失败:$*${OFF}"; echo; [ -n "${ROLLBACK_HINT:-}" ] && echo "还原方法:$ROLLBACK_HINT"; exit 1; }
step() { echo; echo "${GRN}== $* ==${OFF}"; }
ROLLBACK_HINT=""

# ---------------------------------------------------------------- 1
step "1/5 检查环境"
[ "$(id -u)" = "0" ] || die "要用 root 跑"
for c in mysql node npm pm2 nginx python3 curl; do
  command -v "$c" >/dev/null || die "找不到命令:$c"
done
ok "mysql / node $(node -v) / pm2 / nginx / python3 都在"
mysql -e "SELECT 1" >/dev/null 2>&1 || die "连不上 MySQL(root 本地免密),先确认 mysql 服务正常"
ok "MySQL 能连上"
[ -d "$WEB_DIR" ] || die "没有网站目录 $WEB_DIR"
[ -f "$WEB_DIR/index.html" ] || die "没有 $WEB_DIR/index.html"
ok "网站目录正常($(stat -c%s "$WEB_DIR/index.html") 字节)"
[ -f "$NGINX_CONF" ] || die "没有 nginx 配置 $NGINX_CONF"
ok "nginx 配置在"
ss -ltn 2>/dev/null | grep -q ":$PORT " && die "端口 $PORT 已被占用,换个端口再来"
ok "端口 $PORT 空闲"

# ---------------------------------------------------------------- 2
step "2/5 安装后端到 $APP_DIR"
mkdir -p "$APP_DIR"
for f in server.js shim.js schema.sql install.sh patch-console.py nginx-add-api.py; do
  [ -f "$SRC/$f" ] || die "源文件缺失:$SRC/$f"
  cp "$SRC/$f" "$APP_DIR/"
done
ok "文件已复制"
cd "$APP_DIR" || die "进不去 $APP_DIR"
DEPLOY_WRAPPED=1 PORT="$PORT" ORIGINS="https://$DOMAIN,https://www.$DOMAIN" bash install.sh \
  || die "install.sh 没跑成功,看上面的报错"

step "后端自检"
sleep 2
HEALTH=$(curl -sS --max-time 10 "http://127.0.0.1:$PORT/api/health" || true)
echo "$HEALTH" | grep -q '"ok":true' || die "后端没起来。看日志:pm2 logs runadops-api --lines 40"
ok "后端在 127.0.0.1:$PORT 正常"

# ---------------------------------------------------------------- 3
step "3/5 配置 nginx 转发 /api/"
NGX_BAK=""
if grep -q "location /api/" "$NGINX_CONF"; then
  ok "已经配过了,跳过"
else
  OUT=$(python3 "$APP_DIR/nginx-add-api.py" "$NGINX_CONF" "$PORT") || die "改 nginx 配置失败:$OUT"
  echo "$OUT" | sed 's/^/  /'
  NGX_BAK=$(echo "$OUT" | sed -n 's/^BACKUP=//p')
  ROLLBACK_HINT="cp $NGX_BAK $NGINX_CONF && systemctl reload nginx"
  if ! nginx -t >/dev/null 2>&1; then
    cp "$NGX_BAK" "$NGINX_CONF"
    nginx -t 2>&1 | sed 's/^/  /'
    die "nginx -t 没通过,已自动还原配置,网站没受影响"
  fi
  ok "nginx -t 通过"
  systemctl reload nginx || die "reload nginx 失败"
  ok "nginx 已重载"
fi

# ---------------------------------------------------------------- 4
step "4/5 把前端切到 /api"
cd "$WEB_DIR" || die "进不去 $WEB_DIR"
TS=$(date +%Y%m%d-%H%M%S)
cp index.html "index.html.bak-supabase-$TS"
[ -f config.js ] && cp config.js "config.js.bak-supabase-$TS"
ok "已备份 index.html / config.js(后缀 .bak-supabase-$TS)"
ROLLBACK_HINT="cd $WEB_DIR && cp index.html.bak-supabase-$TS index.html && cp config.js.bak-supabase-$TS config.js"

cp "$APP_DIR/shim.js" "$WEB_DIR/shim.js"
ok "shim.js 已就位"
python3 "$APP_DIR/patch-console.py" index.html | sed 's/^/  /' || die "改 index.html 失败"
cat > config.js <<'CFGEOF'
// 自建后端:数据存本机 MySQL，不再连 Supabase。
// 这两个值只是让控制台的"后端已配置"检查通过，真正的地址是同域的 /api。
window.CONFIG = {
  SUPABASE_URL: "https://runadops.com/api",
  SUPABASE_ANON_KEY: "selfhosted"
};
CFGEOF
ok "config.js 已改写"

# ---------------------------------------------------------------- 5
step "5/5 自检"
PUB=$(curl -sS --max-time 15 "https://$DOMAIN/api/health" || true)
if echo "$PUB" | grep -q '"ok":true'; then
  ok "公网 https://$DOMAIN/api/health 通了"
else
  warn "公网接口没通,返回:$PUB"
  warn "本地是通的,多半是 nginx 没重载或者 CDN/防火墙挡了"
fi
STATE=$(curl -sS --max-time 15 "https://$DOMAIN/api/auth/state" || true)
echo "$STATE" | grep -q 'needsSetup' && ok "注册状态接口正常:$STATE"
PAGE=$(curl -sS --max-time 15 "https://$DOMAIN/" || true)
echo "$PAGE" | grep -q 'shim.js' && ok "页面已经在用 shim.js(不再加载 supabase CDN)" \
  || warn "页面里没看到 shim.js,可能有缓存,Ctrl+F5 再看"
echo "$PAGE" | grep -q 'supabase-js' && warn "页面里还有 supabase CDN 引用,检查一下"

pm2 save >/dev/null 2>&1
cat <<EOF

${GRN}================ 装完了 ================${OFF}

现在去浏览器打开 https://$DOMAIN ,按 Ctrl+F5 强制刷新,
用邮箱注册第一个账号 —— 第一个注册的人自动是 owner。

数据存在本机 MySQL 的 runadops 库里,不再经过任何外部服务。

常用命令:
  pm2 logs runadops-api        看后端日志
  pm2 restart runadops-api     重启后端
  cd $APP_DIR && node server.js userlist
  cd $APP_DIR && node server.js useradd 同事邮箱 密码 member
  cd $APP_DIR && node server.js userrole 同事邮箱 admin

要退回 Supabase 版本:
  cd $WEB_DIR && cp index.html.bak-supabase-$TS index.html && cp config.js.bak-supabase-$TS config.js
EOF
if [ -n "$NGX_BAK" ]; then
  echo "  cp $NGX_BAK $NGINX_CONF && systemctl reload nginx   # 撤掉 /api/ 转发"
fi
echo "  pm2 delete runadops-api                              # 停掉后端"
echo
echo "${YEL}建议加个每日备份(复制整行执行):${OFF}"
echo "  echo '0 4 * * * root mysqldump --single-transaction runadops | gzip > /var/backups/runadops-\$(date +\\%F).sql.gz' > /etc/cron.d/runadops-backup"
echo
