# runadops · 操盘控制台

推广代运营用的内部控制台,线上地址 <https://runadops.com>,放在 Vultr 服务器的 `/var/www/runadops/`,数据存 Supabase。

**这个仓库里有两个版本的控制台,别搞混:**

| 目录 | 是什么 | 要不要动 |
|---|---|---|
| `deployed/` | **线上正在跑的那版**,2026-11-19 从 runadops.com 抓下来的快照 | 这是权威版本,更新线上就用它 |
| `console-v2/` | 按《部署与运维手册》重写的一版,尚未上线 | 候选版本,功能范围和线上版不一样,见下 |
| `supabase/schema.sql` | 建表脚本(两版通用) | 在 Supabase SQL Editor 里跑一次 |
| `docs/` | 部署与运维手册 | |

在抓快照之前,这个仓库是空的,线上那份控制台没有任何版本记录——现在有了。

## 两版的差别

两版都用同一套后端:`profiles`(账号角色)+ `records`(`type` + `jsonb` 存全部业务数据),都用 Supabase Auth 登录、realtime 同步。但模块划分不一样,**互不读取对方的数据**:

| | `deployed/`(线上) | `console-v2/` |
|---|---|---|
| 模块 | 概览 / 客户 / 投放项目 / 投放配置 / 收款 / 套餐 / 团队 | 客户 / 投放配置 / 投放项目 / 收款 / 套餐 |
| record type | `client` `campaign` `payment` `package` `brief` `settings` | `client` `project` `payment` `package` `settings` |
| 「投放配置」是什么 | **投放方案库**:按品类存 目标 / 主渠道 / 目标市场 / 受众定向 / 兴趣词 / 投放节奏 / 欢迎语 / 文案 / 素材方向,带预设模板 | 下拉选项维护页:平台、目标、出价方式、收款方式等 10 组选项 |
| 客户关联方式 | `clientId` 存 id,改名不断链 | 存客户名称字符串,改名要同步改 |
| 项目字段 | 总预算 + **已花费**,账户就绪确认(是否用客户自己的户) | 日预算、出价方式、广告户、素材类型 |
| 收款字段 | 6 个(客户/类型/状态/金额/日期/备注) | 10 个(加 币种 / 收款方式 / 关联项目 / 套餐 / 服务周期) |
| 统计 | 概览页 | 收款页合计(已收/待收/本月)、项目页在投预算合计 |
| 导出 | 备份 JSON | 备份 JSON + 各模块 CSV(带 BOM) |
| 大数据量 | `select('*')` 不分页,超 1000 行会被静默截断 | 分页拉取 |

一句话:线上版的**投放方案库和概览**是 `console-v2` 没有的,`console-v2` 的**收款明细、CSV 导出、分页**是线上版没有的。要合并的话,建议以线上版为底座往里加,而不是整体替换。

⚠ **两版的 `config.js` 不通用**:线上版读 `window.CONFIG`,`console-v2` 读 `window.RUNADOPS_CONFIG`。
换版本时忘了一起换配置文件,页面会报「还没配置后端」。

## deployed/index.fixed.html:线上版的三个修复

`deployed/index.fixed.html` 是在线上版基础上改了 3 处(diff 只有 3 个 hunk,其余一字未动):

| 改了什么 | 不改会怎样 | 验证结果 |
|---|---|---|
| 备份文件名 `操盘控制台备份_…` → `runadops-backup-…` | Chromium 丢弃带中文的 `download` 文件名 | 原版存成 `download`(无扩展名),修订版正常 |
| `records` 查询加 `.range()` 分页 | Supabase 默认只返回 1000 行,多的静默丢 | 库里 1500 条:原版只加载 1000,修订版 1500 全到 |
| 锁定 `supabase-js@2.119.1` + unpkg 备用源 | jsdelivr 一挂页面打不开;upstream 发破坏性 2.x 也可能白屏 | 掐断 jsdelivr:原版白屏报错,修订版自动走 unpkg 正常 |

2.119.1 就是现在线上 `@2` 解析到的版本,锁版本不改变当前行为。
三项都用假 Supabase 后端在 Chromium 里实测过,不是推断。

要上线这个修订版:

```bash
scp deployed/index.fixed.html root@139.180.210.215:/var/www/runadops/index.html
```

出问题就用 `deployed/index.html`(原始快照)传回去回滚。

## 更新线上控制台

传上去、刷新网页就生效,不用重启 nginx:

```bash
scp deployed/index.html root@139.180.210.215:/var/www/runadops/index.html
```

`config.js` 里有线上密钥(目前还是占位符),**日常只传 `index.html`**,别顺手把仓库里的占位 `config.js` 覆盖上去。

传完核对一下传对了没有(手册第 5 节那个老问题):

```bash
ssh root@139.180.210.215 "head -3 /var/www/runadops/index.html; ls -l /var/www/runadops/"
```

第 2 行应该是 `<html lang="zh-CN">`。

## 还没做完的事

线上 `config.js` 还是原封不动的模板(`SUPABASE_URL: "在此粘贴你的 Project URL"`),所以**后端还没接上,库里没有任何数据**。接法见 `docs/部署与运维手册.md` 第 3 节:

1. Supabase → SQL Editor → 跑 `supabase/schema.sql`
2. Project Settings → API → 复制 Project URL 和 anon public key
3. `nano /var/www/runadops/config.js` 填进去
4. Ctrl+F5 刷新 → 注册(第一个注册的人自动是 owner)
5. 回 Supabase → Authentication 关掉公开注册,之后用邮箱邀请队友

## 权限

角色在 Supabase → Table Editor → `profiles` → `role` 改:`owner` / `admin` / `member`。owner/admin 能删,member 不能。

⚠ 这条限制**只在界面层**:`schema.sql` 默认的 `records_all_auth` 策略允许任何登录用户删除,会用 API 的人绕得过去。要变成数据库级规则,把 `supabase/schema.sql` 末尾「可选加固」那段取消注释后跑一次(同时会禁止成员自己改自己的角色)。

## 安全

- `anon` key 可以公开(安全靠 RLS),**不要**把数据库密码或 `service_role` key 放进前端或这个仓库。
- 服务器 root 密码、Supabase 账号存密码管理器,不要写进仓库,也不要贴进聊天窗口。
- 同一台服务器上还有 nova323.com 等别的站点,运维只动 `/var/www/runadops/` 和 `sites-available/runadops.com`;改 nginx 永远先 `nginx -t` 再 `systemctl reload nginx`。
