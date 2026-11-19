/* ===========================================================
   runadops 操盘控制台 · 后端配置
   -----------------------------------------------------------
   把下面两行换成你自己的 Supabase 项目信息:
     Supabase → Project Settings → API
       Project URL      → SUPABASE_URL
       anon public key  → SUPABASE_ANON_KEY
   改完存盘,浏览器 Ctrl+F5 刷新即可。
   anon key 可以公开(安全靠数据库 RLS);
   绝对不要把数据库密码或 service_role key 写进这个文件。
   =========================================================== */
window.RUNADOPS_CONFIG = {
  SUPABASE_URL:      "https://你的项目.supabase.co",
  SUPABASE_ANON_KEY: "填你的 anon public key"
};
