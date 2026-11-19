#!/usr/bin/env node
/*
 * runadops 操盘控制台 · 自建后端
 * -------------------------------------------------------------
 * 单文件 Node 服务,数据存本机 MySQL,替代 Supabase。
 * 只依赖 mysql2,其余全用 Node 内置模块(密码哈希用 crypto.scrypt,
 * 不引 bcrypt,免得在服务器上编译原生模块)。
 *
 * 跑起来:  node server.js
 * 配置:    同目录 .env (KEY=VALUE,每行一个)
 * 管理账号: node server.js useradd <邮箱> <密码> [owner|admin|member]
 *          node server.js userrole <邮箱> <角色>
 *          node server.js passwd  <邮箱> <新密码>
 *          node server.js userlist
 *
 * 对外只开 127.0.0.1,由 nginx 反代到 https://runadops.com/api/
 */
'use strict';

const http = require('node:http');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const mysql = require('mysql2/promise');

/* ---------------- 配置 ---------------- */
const ENV_FILE = path.join(__dirname, '.env');
if (fs.existsSync(ENV_FILE)) {
  for (const line of fs.readFileSync(ENV_FILE, 'utf8').split('\n')) {
    // .env 说了算，覆盖继承来的环境变量。
    // 否则 pm2 会一直沿用首次启动时的那份 env，改了 .env 重启也不生效。
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m) process.env[m[1]] = m[2];
  }
}
const CFG = {
  port: Number(process.env.PORT || 8788),
  host: process.env.HOST || '127.0.0.1',
  db: {
    host: process.env.DB_HOST || '127.0.0.1',
    port: Number(process.env.DB_PORT || 3306),
    user: process.env.DB_USER || 'runadops',
    password: process.env.DB_PASS || '',
    database: process.env.DB_NAME || 'runadops',
    connectionLimit: 5,
    charset: 'utf8mb4_general_ci',
  },
  // 允许的来源,防 CSRF。多个用逗号分隔
  origins: (process.env.ORIGINS || 'https://runadops.com').split(',').map(s => s.trim()).filter(Boolean),
  sessionDays: Number(process.env.SESSION_DAYS || 30),
  // 只在本地测试时用:让本服务顺便发静态文件。线上由 nginx 发,留空
  staticDir: process.env.STATIC_DIR || '',
  secureCookie: process.env.SECURE_COOKIE !== '0',
};

let pool;

/* ---------------- 小工具 ---------------- */
const uuid = () => crypto.randomUUID();
const now = () => new Date();

function hashPassword(pw) {
  const salt = crypto.randomBytes(16);
  const key = crypto.scryptSync(String(pw), salt, 64, { N: 16384, r: 8, p: 1 });
  return `scrypt$16384$8$1$${salt.toString('base64')}$${key.toString('base64')}`;
}
function verifyPassword(pw, stored) {
  try {
    const [alg, N, r, p, salt, key] = String(stored).split('$');
    if (alg !== 'scrypt') return false;
    const want = Buffer.from(key, 'base64');
    const got = crypto.scryptSync(String(pw), Buffer.from(salt, 'base64'), want.length,
      { N: Number(N), r: Number(r), p: Number(p) });
    return crypto.timingSafeEqual(want, got);
  } catch { return false; }
}

/* 登录失败限速:同一 IP 15 分钟内最多 10 次失败 */
const failures = new Map();
function tooManyFailures(ip) {
  const f = failures.get(ip);
  if (!f) return false;
  if (Date.now() - f.first > 15 * 60e3) { failures.delete(ip); return false; }
  return f.count >= 10;
}
function noteFailure(ip) {
  const f = failures.get(ip);
  if (!f || Date.now() - f.first > 15 * 60e3) failures.set(ip, { first: Date.now(), count: 1 });
  else f.count++;
}

/* ---------------- HTTP 基础 ---------------- */
function send(res, code, body, headers = {}) {
  const payload = body === null || body === undefined ? '' : JSON.stringify(body);
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    ...headers,
  });
  res.end(payload);
}
const ok = (res, body) => send(res, 200, body === undefined ? { ok: true } : body);
const fail = (res, code, msg) => send(res, code, { error: msg });

function readBody(req, limit = 1024 * 1024) {
  return new Promise((resolve, reject) => {
    let size = 0; const chunks = [];
    req.on('data', c => {
      size += c.length;
      if (size > limit) { reject(new Error('请求体过大')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      if (!raw) return resolve({});
      try { resolve(JSON.parse(raw)); } catch { reject(new Error('JSON 格式不对')); }
    });
    req.on('error', reject);
  });
}
function cookies(req) {
  const out = {};
  for (const part of (req.headers.cookie || '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}
function clientIp(req) {
  return (req.headers['x-forwarded-for'] || '').split(',')[0].trim() || req.socket.remoteAddress || '-';
}

/* 改数据的请求必须带本站 Origin,挡住跨站伪造 */
function originOk(req) {
  const o = req.headers.origin;
  if (!o) return true;                       // 同源的 fetch 可能不带 Origin
  return CFG.origins.includes(o);
}

/* ---------------- 会话 ---------------- */
async function currentUser(req) {
  const token = cookies(req).rad_session;
  if (!token) return null;
  const [rows] = await pool.query(
    `SELECT p.id, p.email, p.name, p.role FROM sessions s
     JOIN profiles p ON p.id = s.user_id
     WHERE s.token = ? AND s.expires_at > NOW()`, [token]);
  return rows[0] || null;
}
async function startSession(res, userId) {
  const token = crypto.randomBytes(32).toString('hex');
  const expires = new Date(Date.now() + CFG.sessionDays * 86400e3);
  await pool.query('INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)', [token, userId, expires]);
  await pool.query('DELETE FROM sessions WHERE expires_at < NOW()');
  const bits = [
    `rad_session=${token}`, 'Path=/', 'HttpOnly', 'SameSite=Lax',
    `Max-Age=${CFG.sessionDays * 86400}`,
  ];
  if (CFG.secureCookie) bits.push('Secure');
  res.setHeader('Set-Cookie', bits.join('; '));
}

/* ---------------- 路由 ---------------- */
const routes = [];
const route = (method, re, handler, opts = {}) => routes.push({ method, re, handler, opts });

/* 健康检查 */
route('GET', /^\/api\/health$/, async (req, res) => {
  await pool.query('SELECT 1');
  ok(res, { ok: true, time: now().toISOString() });
}, { open: true });

/* 还没有人注册时返回 true,控制台据此显示"注册"按钮 */
route('GET', /^\/api\/auth\/state$/, async (req, res) => {
  const [[{ n }]] = await pool.query('SELECT COUNT(*) AS n FROM profiles');
  ok(res, { needsSetup: n === 0 });
}, { open: true });

/* 注册:只有一个人都没有的时候开放,第一个人就是 owner */
route('POST', /^\/api\/auth\/signup$/, async (req, res) => {
  const { email, password, name } = await readBody(req);
  if (!email || !password) return fail(res, 400, '邮箱和密码都要填');
  if (String(password).length < 6) return fail(res, 400, '密码至少 6 位');
  const [[{ n }]] = await pool.query('SELECT COUNT(*) AS n FROM profiles');
  if (n > 0) return fail(res, 403, '公开注册已关闭,请让 owner 给你开账号');
  const id = uuid();
  await pool.query('INSERT INTO profiles (id,email,name,role,pw_hash) VALUES (?,?,?,?,?)',
    [id, String(email).toLowerCase(), name || String(email).split('@')[0], 'owner', hashPassword(password)]);
  await startSession(res, id);
  ok(res, { user: { id, email: String(email).toLowerCase(), name: name || String(email).split('@')[0], role: 'owner' } });
}, { open: true });

route('POST', /^\/api\/auth\/login$/, async (req, res) => {
  const ip = clientIp(req);
  if (tooManyFailures(ip)) return fail(res, 429, '尝试太多次了,等 15 分钟再试');
  const { email, password } = await readBody(req);
  const [rows] = await pool.query('SELECT * FROM profiles WHERE email = ?', [String(email || '').toLowerCase()]);
  const u = rows[0];
  if (!u || !verifyPassword(password, u.pw_hash)) { noteFailure(ip); return fail(res, 401, '邮箱或密码不对'); }
  failures.delete(ip);
  await startSession(res, u.id);
  ok(res, { user: { id: u.id, email: u.email, name: u.name, role: u.role } });
}, { open: true });

route('POST', /^\/api\/auth\/logout$/, async (req, res) => {
  const token = cookies(req).rad_session;
  if (token) await pool.query('DELETE FROM sessions WHERE token = ?', [token]);
  res.setHeader('Set-Cookie', 'rad_session=; Path=/; HttpOnly; Max-Age=0');
  ok(res);
}, { open: true });

route('GET', /^\/api\/me$/, async (req, res, user) => ok(res, { user }));

/* ---------- 业务数据 ---------- */
route('GET', /^\/api\/records$/, async (req, res) => {
  // 支持 ?offset=&limit=,前端分页拉取时用(替身层把 supabase 的 .range() 映射到这里)
  const q = new URL(req.url, 'http://x').searchParams;
  const limit = Math.min(Math.max(parseInt(q.get('limit') || '5000', 10) || 5000, 1), 5000);
  const offset = Math.max(parseInt(q.get('offset') || '0', 10) || 0, 0);
  const [rows] = await pool.query(
    'SELECT id, type, data, updated_at, updated_by FROM records ORDER BY updated_at DESC LIMIT ? OFFSET ?',
    [limit, offset]);
  ok(res, {
    records: rows.map(r => ({
      id: r.id, type: r.type,
      data: typeof r.data === 'string' ? JSON.parse(r.data) : r.data,
      updated_at: r.updated_at, updated_by: r.updated_by,
    })),
  });
});

/* 轮询用:只回一个很小的指纹,变了前端再去拉完整数据 */
route('GET', /^\/api\/records\/stamp$/, async (req, res) => {
  const [[row]] = await pool.query('SELECT COUNT(*) AS n, COALESCE(MAX(updated_at),0) AS t FROM records');
  ok(res, { n: row.n, t: String(row.t) });
});

route('POST', /^\/api\/records$/, async (req, res, user) => {
  const { id, type, data } = await readBody(req);
  if (!type) return fail(res, 400, '缺 type');
  const rid = id || uuid();
  await pool.query('INSERT INTO records (id,type,data,updated_by) VALUES (?,?,CAST(? AS JSON),?)',
    [rid, String(type), JSON.stringify(data || {}), user.id]);
  const [[row]] = await pool.query('SELECT id,type,data,updated_at,updated_by FROM records WHERE id=?', [rid]);
  ok(res, { record: { ...row, data: typeof row.data === 'string' ? JSON.parse(row.data) : row.data } });
});

route('PUT', /^\/api\/records\/([\w-]+)$/, async (req, res, user, m) => {
  const { data } = await readBody(req);
  const [r] = await pool.query('UPDATE records SET data=CAST(? AS JSON), updated_by=? WHERE id=?',
    [JSON.stringify(data || {}), user.id, m[1]]);
  if (!r.affectedRows) return fail(res, 404, '没有这条记录');
  const [[row]] = await pool.query('SELECT id,type,data,updated_at,updated_by FROM records WHERE id=?', [m[1]]);
  ok(res, { record: { ...row, data: typeof row.data === 'string' ? JSON.parse(row.data) : row.data } });
});

/* 删除:owner / admin 才行 —— 这条规则在服务端,前端绕不过去 */
route('DELETE', /^\/api\/records\/([\w-]+)$/, async (req, res, user, m) => {
  if (user.role !== 'owner' && user.role !== 'admin') return fail(res, 403, '只有 owner / admin 能删除');
  const [r] = await pool.query('DELETE FROM records WHERE id=?', [m[1]]);
  if (!r.affectedRows) return fail(res, 404, '没有这条记录');
  ok(res);
});

/* ---------- AI 生成投放物料 ---------- */
route('POST', /^\/api\/ai\/brief$/, async (req, res, user) => {
  const body = await readBody(req);
  let brief = {};
  if (body.briefId) {
    const [rows] = await pool.query("SELECT data FROM records WHERE id=? AND type='brief'", [body.briefId]);
    if (rows[0]) brief = typeof rows[0].data === 'string' ? JSON.parse(rows[0].data) : rows[0].data;
  }
  Object.assign(brief, body.fields || {});
  if (body.product !== undefined) brief.product = body.product;
  if (body.extra !== undefined) brief.extra = body.extra;

  let ai;
  try {
    ai = require('./ai.js');
  } catch (e) {
    return fail(res, 500, 'AI 模块没装好:' + e.message + ' —— 在 ' + __dirname + ' 下跑 npm install @anthropic-ai/sdk zod');
  }
  try {
    const out = await ai.generate(brief);
    console.log('[ai] ' + user.email + ' 生成 "' + (brief.project || '(无名)') + '" 用了 '
      + out.usage.input_tokens + '+' + out.usage.output_tokens + ' token,约 $' + out.usage.cost_usd);
    ok(res, out);
  } catch (e) {
    console.error('[ai]', e.code || '', e.message);
    fail(res, e.code === 'NO_KEY' ? 400 : 502, e.message);
  }
});

/* ---------- 团队 ---------- */
route('GET', /^\/api\/users$/, async (req, res) => {
  const [rows] = await pool.query('SELECT id,email,name,role,created_at FROM profiles ORDER BY created_at ASC');
  ok(res, { users: rows });
});

route('POST', /^\/api\/users$/, async (req, res, user) => {
  if (user.role !== 'owner' && user.role !== 'admin') return fail(res, 403, '只有 owner / admin 能加人');
  const { email, password, name, role } = await readBody(req);
  if (!email || !password) return fail(res, 400, '邮箱和密码都要填');
  if (String(password).length < 6) return fail(res, 400, '密码至少 6 位');
  const r = ['owner', 'admin', 'member'].includes(role) ? role : 'member';
  if (r === 'owner' && user.role !== 'owner') return fail(res, 403, '只有 owner 能再指定 owner');
  const id = uuid();
  try {
    await pool.query('INSERT INTO profiles (id,email,name,role,pw_hash) VALUES (?,?,?,?,?)',
      [id, String(email).toLowerCase(), name || String(email).split('@')[0], r, hashPassword(password)]);
  } catch (e) {
    if (e.code === 'ER_DUP_ENTRY') return fail(res, 409, '这个邮箱已经有账号了');
    throw e;
  }
  ok(res, { user: { id, email: String(email).toLowerCase(), name, role: r } });
});

route('PATCH', /^\/api\/users\/([\w-]+)$/, async (req, res, user, m) => {
  const body = await readBody(req);
  const target = m[1];
  const isSelf = target === user.id;
  const isBoss = user.role === 'owner' || user.role === 'admin';
  if (!isSelf && !isBoss) return fail(res, 403, '只能改自己');
  const sets = [], vals = [];
  if (body.name !== undefined) { sets.push('name=?'); vals.push(String(body.name).slice(0, 100)); }
  if (body.password !== undefined) {
    if (String(body.password).length < 6) return fail(res, 400, '密码至少 6 位');
    if (!isSelf && user.role !== 'owner') return fail(res, 403, '只有 owner 能改别人的密码');
    sets.push('pw_hash=?'); vals.push(hashPassword(body.password));
  }
  if (body.role !== undefined) {
    if (user.role !== 'owner') return fail(res, 403, '只有 owner 能改角色');
    if (isSelf) return fail(res, 400, '不能改自己的角色,免得把自己锁在外面');
    if (!['owner', 'admin', 'member'].includes(body.role)) return fail(res, 400, '角色只能是 owner/admin/member');
    sets.push('role=?'); vals.push(body.role);
  }
  if (!sets.length) return fail(res, 400, '没有要改的内容');
  vals.push(target);
  const [r] = await pool.query(`UPDATE profiles SET ${sets.join(',')} WHERE id=?`, vals);
  if (!r.affectedRows) return fail(res, 404, '没有这个人');
  if (body.password !== undefined) await pool.query('DELETE FROM sessions WHERE user_id=?', [target]);
  ok(res);
});

route('DELETE', /^\/api\/users\/([\w-]+)$/, async (req, res, user, m) => {
  if (user.role !== 'owner') return fail(res, 403, '只有 owner 能删人');
  if (m[1] === user.id) return fail(res, 400, '不能删自己');
  await pool.query('DELETE FROM sessions WHERE user_id=?', [m[1]]);
  const [r] = await pool.query('DELETE FROM profiles WHERE id=?', [m[1]]);
  if (!r.affectedRows) return fail(res, 404, '没有这个人');
  ok(res);
});

/* ---------------- 静态文件(只用于本地测试) ---------------- */
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8' };
function serveStatic(req, res, pathname) {
  if (!CFG.staticDir) return false;
  const rel = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
  const file = path.resolve(CFG.staticDir, rel);
  if (!file.startsWith(path.resolve(CFG.staticDir))) { fail(res, 403, 'nope'); return true; }
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) return false;
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
  res.end(fs.readFileSync(file));
  return true;
}

/* ---------------- 主循环 ---------------- */
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  const pathname = url.pathname.replace(/\/+$/, '') || '/';

  if (!pathname.startsWith('/api')) {
    if (serveStatic(req, res, url.pathname)) return;
    return fail(res, 404, '没有这个地址');
  }

  const mutating = req.method !== 'GET' && req.method !== 'HEAD';
  if (mutating && !originOk(req)) return fail(res, 403, '来源不对');

  for (const r of routes) {
    if (r.method !== req.method) continue;
    const m = pathname.match(r.re);
    if (!m) continue;
    try {
      let user = null;
      if (!r.opts.open) {
        user = await currentUser(req);
        if (!user) return fail(res, 401, '没登录');
      }
      return await r.handler(req, res, user, m);
    } catch (e) {
      console.error('[err]', req.method, pathname, e.message);
      return fail(res, 500, '服务器出错:' + e.message);
    }
  }
  fail(res, 404, '没有这个接口');
});

/* ---------------- 命令行:管账号 ---------------- */
async function cli(args) {
  const [cmd, ...rest] = args;
  const roleOf = v => (['owner', 'admin', 'member'].includes(v) ? v : 'member');
  if (cmd === 'useradd') {
    const [email, pw, role] = rest;
    if (!email || !pw) { console.error('用法: node server.js useradd <邮箱> <密码> [owner|admin|member]'); process.exit(1); }
    await pool.query('INSERT INTO profiles (id,email,name,role,pw_hash) VALUES (?,?,?,?,?)',
      [uuid(), email.toLowerCase(), email.split('@')[0], roleOf(role), hashPassword(pw)]);
    console.log('已添加', email, '角色', roleOf(role));
  } else if (cmd === 'userrole') {
    const [email, role] = rest;
    const [r] = await pool.query('UPDATE profiles SET role=? WHERE email=?', [roleOf(role), email.toLowerCase()]);
    console.log(r.affectedRows ? `${email} 角色改为 ${roleOf(role)}` : '没找到这个邮箱');
  } else if (cmd === 'passwd') {
    const [email, pw] = rest;
    const [r] = await pool.query('UPDATE profiles SET pw_hash=? WHERE email=?', [hashPassword(pw), email.toLowerCase()]);
    await pool.query('DELETE FROM sessions WHERE user_id IN (SELECT id FROM profiles WHERE email=?)', [email.toLowerCase()]);
    console.log(r.affectedRows ? `${email} 密码已改` : '没找到这个邮箱');
  } else if (cmd === 'aicheck') {
    // 验证 ANTHROPIC_API_KEY 能不能用（会真的发一次最小请求，花费不到 1 分钱）
    if (!process.env.ANTHROPIC_API_KEY) {
      console.error('没配 ANTHROPIC_API_KEY。把它写进 ' + ENV_FILE + ' 再试');
      await pool.end(); process.exit(1);
    }
    const kv = process.env.ANTHROPIC_API_KEY;
    console.log('key 长度 ' + kv.length + ',开头 ' + kv.slice(0, 12) + '…(正常是 100 出头，太短说明粘贴时被截断了)');
    try {
      const AnthropicPkg = require('@anthropic-ai/sdk');
      const Anthropic = AnthropicPkg.default || AnthropicPkg;
      const c = new Anthropic({ apiKey: kv });
      const r = await c.messages.create({
        model: process.env.AI_MODEL || 'claude-opus-5-5',
        max_tokens: 16,
        messages: [{ role: 'user', content: '回复 ok 两个字母，不要别的' }],
      });
      const txt = (r.content.find(b => b.type === 'text') || {}).text || '';
      console.log('调用成功,模型回了:' + JSON.stringify(txt.trim()));
      console.log('用了 ' + r.usage.input_tokens + '+' + r.usage.output_tokens + ' token。AI 功能可用。');
    } catch (e) {
      console.error('调用失败:' + e.message);
      if (/401|authentication/i.test(e.message)) console.error('多半是 key 不对或被截断了,重新写一次');
      await pool.end(); process.exit(1);
    }
  } else if (cmd === 'userlist') {
    const [rows] = await pool.query('SELECT email,name,role,created_at FROM profiles ORDER BY created_at');
    if (!rows.length) console.log('(还没有账号)');
    rows.forEach(u => console.log(`${u.role.padEnd(6)} ${u.email}  ${u.name || ''}`));
  } else {
    console.error('可用命令: useradd / userrole / passwd / userlist / aicheck');
    process.exit(1);
  }
  await pool.end();
}

/* ---------------- 启动 ---------------- */
(async () => {
  pool = mysql.createPool(CFG.db);
  try {
    await pool.query('SELECT 1');
  } catch (e) {
    console.error('连不上 MySQL:', e.message);
    console.error('检查同目录 .env 里的 DB_USER / DB_PASS / DB_NAME');
    process.exit(1);
  }
  const args = process.argv.slice(2);
  if (args.length) return cli(args);
  server.listen(CFG.port, CFG.host, () => {
    console.log(`runadops api 已启动 http://${CFG.host}:${CFG.port}  库=${CFG.db.database}  允许来源=${CFG.origins.join(',')}`);
  });
})();
