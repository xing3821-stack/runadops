# runadops · 操盘控制台

推广代运营用的内部控制台:**客户 / 投放配置 / 投放项目 / 收款 / 套餐**。全员各自邮箱登录,看同一套数据。

- 前端:一个 `index.html`,放在自己的 Vultr 服务器(nginx),不需要构建、不需要 node
- 后端:Supabase(Auth 管登录,Postgres 存数据,Realtime 做多人同步)
- 线上:<https://runadops.com>

## 文件

| 文件 | 作用 |
|---|---|
| `index.html` | 控制台本体(约 46KB,单文件,自带样式和逻辑) |
| `config.js` | 只放 Supabase `Project URL` + `anon public` key |
| `supabase/schema.sql` | 建表脚本,在 Supabase SQL Editor 里跑一次 |

## 第一次部署

1. **建库**:Supabase → SQL Editor → New query → 粘贴 `supabase/schema.sql` 全文 → Run。
2. **传文件**到服务器 `/var/www/runadops/`:

```bash
scp index.html config.js root@139.180.210.215:/var/www/runadops/
```

3. **填密钥**(在服务器上改,`Project Settings → API` 里复制):

```bash
ssh root@139.180.210.215 'nano /var/www/runadops/config.js'
```

4. 打开 <https://runadops.com> 按 Ctrl+F5 → 用邮箱**注册**(第一个注册的人自动是 owner)→ 进「投放配置」点「载入预设」→ 点「保存配置」。
5. 回 Supabase → Authentication → 关掉公开注册,之后用邮箱邀请队友。

## 日常更新控制台

改完 `index.html`,传上去、刷新网页就生效,不用重启 nginx:

```bash
scp index.html root@139.180.210.215:/var/www/runadops/index.html
```

`config.js` 里有线上密钥,**日常只传 `index.html`**,别顺手把仓库里的占位 `config.js` 覆盖上去。

## 怎么用

- **投放配置**:这一页定义其他页面所有下拉框的选项(平台、投放目标、出价方式、收费方式、收款方式、状态…)。「载入预设」填入一套常用默认值,**点「保存配置」才真正写进数据库**,改完全团队立刻生效。
- **套餐 → 客户 → 投放项目 → 收款**:建议按这个顺序建。客户的套餐、项目的客户、收款的客户/项目,都是从已有数据里选,不用手打。
- **收款**只记我们的服务费/管理费,不记客户账户里的广告消耗;投放项目里的「日预算」才是客户户的消耗预算,「广告户」一律填客户自有户。
- **备份**(左下角):把全部数据导出成一个 JSON 存档。每个列表页右上角还能导出当前筛选结果的 CSV(带 BOM,Excel 双击不乱码)。
- 快捷键:`n` 新建、`/` 跳到搜索框。

## 权限

角色在 Supabase → Table Editor → `profiles` → `role` 里改,三种:`owner` / `admin` / `member`。

- owner / admin:能增、能改、能删
- member:能增、能改,删除按钮是灰的(防手滑)

⚠ **这条限制目前只在界面层**:`schema.sql` 默认的 `records_all_auth` 策略允许任何登录用户删除,会用 API 的人绕得过去。要把它变成数据库级规则,把 `supabase/schema.sql` 末尾「可选加固」那一段取消注释后在 SQL Editor 跑一次(同时会禁止成员自己改自己的角色)。

## 离线 / CDN 打不开

`index.html` 从 CDN 加载 supabase-js(jsdelivr,失败自动换 unpkg)。如果办公网连不上这两个 CDN,把这个文件下载后放到网站同目录即可自动改用本地版:

```bash
curl -o supabase.js https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js
scp supabase.js root@139.180.210.215:/var/www/runadops/supabase.js
```

## 数据怎么存的

两张表(详见 `supabase/schema.sql`):

- `profiles` — 账号与角色,由注册触发器自动建档,第一个注册的人是 owner
- `records` — 全部业务数据,`type` 区分种类(`client` / `package` / `project` / `payment` / `settings`),`data` 是 jsonb

加字段不用改数据库:在 `index.html` 的 `MODULES` 里给对应模块的 `fields` 加一项即可,表单、表格、CSV 导出都会自动跟上。

## 安全

- `anon` key 可以公开(安全靠数据库 RLS),**不要**把数据库密码或 `service_role` key 放进前端或这个仓库。
- 服务器 root 密码、Supabase 账号密码存自己的密码管理器,不要写进仓库。
- 同一台服务器上还有别的站点,运维时只动 `/var/www/runadops/` 和 `sites-available/runadops.com`;改 nginx 永远先 `nginx -t` 再 `systemctl reload nginx`。
