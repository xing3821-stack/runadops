# 线上版

- `index.fixed.html` — **2026-11-19 14:28 起线上正在跑的就是这份**(46,938 字节,
  sha256 `09e3a09f…`)。用 `patch-live.py` 在服务器上就地生成,与本文件字节一致,
  已从公网抓回核对。
- `index.html` — 修订**之前**的原版快照(46,604 字节),等同于服务器上的
  `/var/www/runadops/index.html.bak`,回滚用。
- `patch-live.py` — 就地修订脚本,不用传文件,ssh 进服务器跑即可。

原始说明(抓快照时):2026-11-19 直接从 <https://runadops.com> 抓下来的。

- `index.html` — 控制台本体,46,604 字节
  sha256 `82abb43b18605ae966152ec49f5bf7fc5ad4fecc6c1793ee249460265b9d2adf`
- `config.js` — 线上的配置文件,抓下来时**还是占位符**
  (URL 写的是 `abcd.supabase.co`,anon key 没填),所以不含任何真实密钥

## 当初体检出的三个问题(均已修复并上线)

1. **备份文件名是中文** —— `a.download='操盘控制台备份_…json'`。Chromium 会把带非 ASCII
   的 `download` 文件名整个丢掉,存成一个叫 `download` 的无扩展名文件。改成纯 ASCII 即可。
2. **`records` 查询不分页** —— `supa.from('records').select('*')` 没有 `.range()`。
   Supabase REST 默认最多返回 1000 行,数据攒够以后会被静默截断,界面上看不出来。
3. **CDN 没锁版本** —— `supabase-js@2` 取的是最新 2.x,upstream 出破坏性变更就可能白屏;
   而且只有 jsdelivr 一个源,连不上就打不开。

上线验证(2026-11-19 14:30,真实浏览器打开 https://runadops.com):
页面正常、登录页可见、零 JS 报错、supabase 库从锁定版本的 jsdelivr 加载成功。

回滚:`cd /var/www/runadops && cp index.html.bak index.html`

## index.fixed.html

上面三个问题的修订版,只改了 3 处,其余与 `index.html` 完全一致
(`diff -u index.html index.fixed.html` 只有 3 个 hunk)。

实测结果(假 Supabase 后端 + Chromium):

| | 原版 | 修订版 |
|---|---|---|
| 库里 1500 条记录 | 只加载 1000 条,界面无提示 | 1500 条全部加载 |
| 点「备份」 | 存成无扩展名的 `download` | `runadops-backup-2026-11-19.json` |
| jsdelivr 不可达 | 白屏,`window.supabase` undefined,控制台报错 | 自动走 unpkg,正常进登录页 |

锁定的 2.119.1 就是现在线上 `@2` 解析到的版本,所以锁版本本身不改变行为。

上线:`scp index.fixed.html root@139.180.210.215:/var/www/runadops/index.html`
回滚:`scp index.html root@139.180.210.215:/var/www/runadops/index.html`

另:线上版读的配置全局变量是 `window.CONFIG`,而 `console-v2/` 读的是
`window.RUNADOPS_CONFIG`,两边的 config.js 不能互换。
