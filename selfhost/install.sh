#!/bin/bash
# runadops 自建后端 · 安装脚本
# 在服务器上: cd /opt/runadops-api && bash install.sh
set -e
cd "$(dirname "$0")"

# 可被外面的环境变量覆盖（deploy.sh 会传）
DB_NAME=${DB_NAME:-runadops}
DB_USER=${DB_USER:-runadops}
PORT=${PORT:-8788}
ORIGINS=${ORIGINS:-https://runadops.com,https://www.runadops.com}

echo "== 1/5 建库建表 =="
mysql < schema.sql

echo "== 2/5 建数据库账号 =="
if [ -f .env ] && grep -q '^DB_PASS=' .env; then
  DB_PASS=$(grep '^DB_PASS=' .env | cut -d= -f2-)
  echo "   沿用 .env 里已有的密码"
else
  DB_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)
fi
mysql -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
          ALTER USER '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
          GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'127.0.0.1';
          FLUSH PRIVILEGES;"

echo "== 3/5 写配置 =="
cat > .env <<ENVEOF
PORT=${PORT}
HOST=127.0.0.1
DB_HOST=127.0.0.1
DB_USER=${DB_USER}
DB_PASS=${DB_PASS}
DB_NAME=${DB_NAME}
ORIGINS=${ORIGINS}
SESSION_DAYS=30
ENVEOF
chmod 600 .env
echo "   .env 已写入(权限 600,只有 root 能看)"

echo "== 4/5 装依赖 =="
npm install --omit=dev --no-fund --no-audit mysql2 >/dev/null 2>&1
echo "   mysql2 装好了"

echo "== 5/5 用 pm2 跑起来 =="
pm2 delete runadops-api >/dev/null 2>&1 || true
pm2 start server.js --name runadops-api
pm2 save >/dev/null

sleep 2
echo
echo "== 自检 =="
curl -sS "http://127.0.0.1:${PORT}/api/health" && echo
curl -sS "http://127.0.0.1:${PORT}/api/auth/state" && echo
if [ -z "${DEPLOY_WRAPPED:-}" ]; then
  echo
  echo "后端装好了。接下来还差两步:"
  echo "  1) nginx 里把 /api/ 转发到 127.0.0.1:${PORT}"
  echo "  2) 把 shim.js 和改过的 index.html 放进 ${WEB_DIR:-/var/www/runadops}/"
fi
