# 自建后端(替代 Supabase)

数据放自己服务器的 MySQL,不依赖外部服务。控制台代码几乎不用改——
`shim.js` 冒充 supabase-js,把原来的调用转成请求 `/api`。

```
浏览器 → https://runadops.com/api/... → nginx 反代 → 127.0.0.1:8788 (node) → MySQL
```

## 文件

| 文件 | 作用 |
|---|---|
| `server.js` | 后端本体,单文件,只依赖 mysql2。登录、权限、数据读写、轮询用的指纹接口 |
| `shim.js` | 浏览器端替身层,放进 `/var/www/runadops/`,控制台加载它代替 supabase-js |
| `schema.sql` | 建库建表(`profiles` / `records` / `sessions`) |
| `install.sh` | 一键安装:建库、建数据库账号、写 .env、装依赖、pm2 拉起 |
| `patch-console.py` | 把控制台的 supabase-js script 标签换成 `shim.js`,只改这一处 |

## 安装

一条命令装完(建库、建账号、写配置、pm2 拉起、配 nginx、切前端、自检):

```bash
bash deploy.sh
```

每一步都先备份,失败就停下并告诉你怎么还原;nginx 改完先 `nginx -t`,
不通过自动还原配置,网站不会受影响。只动 `/opt/runadops-api`、
`/var/www/runadops/` 和 `sites-available/runadops.com` 这三处。

想分步来也行:`install.sh` 只装后端,`nginx-add-api.py` 只改 nginx,
`patch-console.py` 只切前端。

deploy.sh 会自动加下面这段;要手工加也可以,在 `runadops.com` 的 443 server 块里:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8788;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

`nginx -t` 通过后 `systemctl reload nginx`。最后把前端换过去:

```bash
cp /opt/runadops-api/shim.js /var/www/runadops/
cd /var/www/runadops && python3 /opt/runadops-api/patch-console.py index.html
printf 'window.CONFIG = {\n  SUPABASE_URL: "https://runadops.com/api",\n  SUPABASE_ANON_KEY: "selfhosted"\n};\n' > config.js
```

刷新网页 → 注册第一个账号(自动是 owner)。

## 管账号

控制台界面里没有改角色的地方(原本是去 Supabase 后台改),改用命令行:

```bash
cd /opt/runadops-api
node server.js userlist                              # 看都有谁
node server.js useradd tongshi@abc.com 密码 member    # 加人
node server.js userrole tongshi@abc.com admin        # 改角色
node server.js passwd tongshi@abc.com 新密码          # 重置密码
```

## 和 Supabase 版的差别

| | Supabase | 自建 |
|---|---|---|
| 数据在哪 | Supabase 云 | 你服务器的 MySQL |
| 实时同步 | WebSocket 推送 | 轮询,10 秒一次 + 切回窗口立刻查 |
| 「member 不能删」 | 只在界面层,会用 API 的人绕得过 | **服务端强制**,绕不过 |
| 备份 | Supabase 每日自动 + 控制台导出 | 控制台导出 + 你自己给 MySQL 配定时备份 |
| 改角色 | Supabase 后台点一下 | 命令行一条 |

⚠ **备份要自己做**。Supabase 原本每天自动备份,自建之后没人替你做了。建议加个 cron:

```bash
echo '0 4 * * * root mysqldump --single-transaction runadops | gzip > /var/backups/runadops-$(date +\%F).sql.gz && find /var/backups -name "runadops-*.sql.gz" -mtime +30 -delete' > /etc/cron.d/runadops-backup
```

## 验证情况

本地用真的 MySQL 8 + 真实控制台页面跑 Playwright 端到端,27 项全过:
注册第一人即 owner、密码存哈希、数据真的落到 MySQL、刷新保持登录、
改库后界面 10 秒内自动同步、备份导出、密码错误拒绝登录、
member 调接口删除被 403 挡住、member 不能提权、未登录读不到数据(401)、
1502 条记录分页全部拉到、全程无 JS 报错。

## 两个踩过的坑(已修)

- **pm2 会记住首次启动时的环境变量**,后来改 `.env` 再 `pm2 restart` 不生效。
  所以 `server.js` 改成 `.env` 文件优先,覆盖继承来的变量。
- **CSRF 来源检查**:改数据的请求必须带本站 Origin。`.env` 里的 `ORIGINS`
  要和实际访问的域名一致,不然会报「来源不对」。deploy.sh 会自动写成
  `https://runadops.com,https://www.runadops.com`。
