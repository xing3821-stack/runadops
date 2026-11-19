# 线上版快照

2026-11-19 直接从 <https://runadops.com> 抓下来的,就是服务器
`/var/www/runadops/` 里正在跑的那份。

- `index.html` — 控制台本体,46,604 字节
  sha256 `82abb43b18605ae966152ec49f5bf7fc5ad4fecc6c1793ee249460265b9d2adf`
- `config.js` — 线上的配置文件,抓下来时**还是占位符**
  (URL 写的是 `abcd.supabase.co`,anon key 没填),所以不含任何真实密钥

## 已知问题(抓快照时体检出来的,还没修)

1. **备份文件名是中文** —— `a.download='操盘控制台备份_…json'`。Chromium 会把带非 ASCII
   的 `download` 文件名整个丢掉,存成一个叫 `download` 的无扩展名文件。改成纯 ASCII 即可。
2. **`records` 查询不分页** —— `supa.from('records').select('*')` 没有 `.range()`。
   Supabase REST 默认最多返回 1000 行,数据攒够以后会被静默截断,界面上看不出来。
3. **CDN 没锁版本** —— `supabase-js@2` 取的是最新 2.x,upstream 出破坏性变更就可能白屏;
   而且只有 jsdelivr 一个源,连不上就打不开。

改之前先把这份快照留着,方便回滚。
