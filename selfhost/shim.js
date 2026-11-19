/*
 * supabase-js 替身层
 * -------------------------------------------------------------
 * 控制台原本用 supabase-js 直连 Supabase。这个文件冒充它,
 * 把同样的调用转成请求本服务器的 /api。控制台代码几乎不用改,
 * 只要把原来加载 supabase-js 的 <script> 换成这个文件。
 *
 * 只实现控制台真正用到的那部分 API,不是完整的 supabase-js。
 */
(function () {
  'use strict';

  var API = (window.RUNADOPS_API || '/api').replace(/\/+$/, '');
  var me = null;                 // 当前登录用户 {id,email,name,role}
  var authCb = null;             // onAuthStateChange 的回调

  function req(method, path, body) {
    var opts = {
      method: method,
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' },
    };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(API + path, opts).then(function (r) {
      return r.text().then(function (t) {
        var j = {};
        try { j = t ? JSON.parse(t) : {}; } catch (e) { j = { error: '返回的不是 JSON:' + t.slice(0, 80) }; }
        return { status: r.status, ok: r.ok, body: j };
      });
    });
  }
  function errOf(res) {
    if (res.ok) return null;
    return { message: res.body && res.body.error ? res.body.error : ('请求失败 (' + res.status + ')'), status: res.status };
  }
  function sessionOf(user) {
    if (!user) return null;
    return {
      access_token: 'self-hosted',
      user: { id: user.id, email: user.email, user_metadata: { name: user.name }, role: user.role },
    };
  }
  function fireAuth(evt, session) {
    if (authCb) { try { authCb(evt, session); } catch (e) { console.error(e); } }
  }

  /* ---------------- auth ---------------- */
  var auth = {
    getSession: function () {
      return req('GET', '/me').then(function (r) {
        me = r.ok ? r.body.user : null;
        return { data: { session: sessionOf(me) }, error: null };
      });
    },
    getUser: function () {
      return auth.getSession().then(function (r) {
        return { data: { user: r.data.session ? r.data.session.user : null }, error: null };
      });
    },
    onAuthStateChange: function (cb) {
      authCb = cb;
      return { data: { subscription: { unsubscribe: function () { authCb = null; } } } };
    },
    signInWithPassword: function (c) {
      return req('POST', '/auth/login', { email: c.email, password: c.password }).then(function (r) {
        if (!r.ok) return { data: { session: null, user: null }, error: errOf(r) };
        me = r.body.user;
        var s = sessionOf(me);
        setTimeout(function () { fireAuth('SIGNED_IN', s); }, 0);
        return { data: { session: s, user: s.user }, error: null };
      });
    },
    signUp: function (c) {
      var name = c.options && c.options.data ? c.options.data.name : undefined;
      return req('POST', '/auth/signup', { email: c.email, password: c.password, name: name }).then(function (r) {
        if (!r.ok) return { data: { session: null, user: null }, error: errOf(r) };
        me = r.body.user;
        var s = sessionOf(me);
        setTimeout(function () { fireAuth('SIGNED_IN', s); }, 0);
        return { data: { session: s, user: s.user }, error: null };
      });
    },
    signOut: function () {
      return req('POST', '/auth/logout').then(function (r) {
        me = null;
        setTimeout(function () { fireAuth('SIGNED_OUT', null); }, 0);
        return { error: errOf(r) };
      });
    },
    // 控制台没用到，占位免得报错
    resetPasswordForEmail: function () { return Promise.resolve({ data: {}, error: null }); },
  };

  /* ---------------- from(table) 查询构造器 ---------------- */
  function builder(table) {
    var st = { table: table, op: 'select', payload: null, filters: {}, single: false, range: null };

    function exec() {
      if (st.table === 'records') return records();
      if (st.table === 'profiles') return profiles();
      return Promise.resolve({ data: null, error: { message: '替身层不认识这张表: ' + st.table } });
    }

    function records() {
      if (st.op === 'select') {
        var qs = '';
        if (st.range) qs = '?offset=' + st.range[0] + '&limit=' + (st.range[1] - st.range[0] + 1);
        return req('GET', '/records' + qs).then(function (r) {
          if (!r.ok) return { data: null, error: errOf(r) };
          var rows = r.body.records || [];
          if (st.filters.id) rows = rows.filter(function (x) { return x.id === st.filters.id; });
          if (st.filters.type) rows = rows.filter(function (x) { return x.type === st.filters.type; });
          return { data: st.single ? (rows[0] || null) : rows, error: null };
        });
      }
      if (st.op === 'insert') {
        var p = st.payload || {};
        return req('POST', '/records', { id: p.id, type: p.type, data: p.data }).then(function (r) {
          if (!r.ok) return { data: null, error: errOf(r) };
          return { data: st.single ? r.body.record : [r.body.record], error: null };
        });
      }
      if (st.op === 'update') {
        if (!st.filters.id) return Promise.resolve({ data: null, error: { message: '更新必须指定 id' } });
        return req('PUT', '/records/' + encodeURIComponent(st.filters.id), { data: (st.payload || {}).data }).then(function (r) {
          if (!r.ok) return { data: null, error: errOf(r) };
          return { data: st.single ? r.body.record : [r.body.record], error: null };
        });
      }
      if (st.op === 'delete') {
        if (!st.filters.id) return Promise.resolve({ data: null, error: { message: '删除必须指定 id' } });
        return req('DELETE', '/records/' + encodeURIComponent(st.filters.id)).then(function (r) {
          return { data: null, error: errOf(r) };
        });
      }
      return Promise.resolve({ data: null, error: { message: '不支持的操作' } });
    }

    function profiles() {
      if (st.op === 'select') {
        // 查自己：直接用 /me，省一次全量
        if (st.filters.id && me && st.filters.id === me.id) {
          return Promise.resolve({ data: st.single ? me : [me], error: null });
        }
        return req('GET', '/users').then(function (r) {
          if (!r.ok) return { data: null, error: errOf(r) };
          var rows = r.body.users || [];
          if (st.filters.id) rows = rows.filter(function (x) { return x.id === st.filters.id; });
          return { data: st.single ? (rows[0] || null) : rows, error: null };
        });
      }
      if (st.op === 'insert') {
        // 账号由后端在注册时就建好了，这里无事可做
        return Promise.resolve({ data: st.payload, error: null });
      }
      if (st.op === 'update') {
        var id = st.filters.id || (me && me.id);
        if (!id) return Promise.resolve({ data: null, error: { message: '不知道要改谁' } });
        return req('PATCH', '/users/' + encodeURIComponent(id), st.payload || {}).then(function (r) {
          if (r.ok && me && id === me.id && st.payload && st.payload.name !== undefined) me.name = st.payload.name;
          return { data: null, error: errOf(r) };
        });
      }
      if (st.op === 'delete') {
        if (!st.filters.id) return Promise.resolve({ data: null, error: { message: '删除必须指定 id' } });
        return req('DELETE', '/users/' + encodeURIComponent(st.filters.id)).then(function (r) {
          return { data: null, error: errOf(r) };
        });
      }
      return Promise.resolve({ data: null, error: { message: '不支持的操作' } });
    }

    var api = {
      select: function () { if (st.op === 'select') st.op = 'select'; return api; },
      order: function () { return api; },
      limit: function () { return api; },
      range: function (a, b) { st.range = [a, b]; return api; },
      eq: function (col, val) { st.filters[col] = val; return api; },
      maybeSingle: function () { st.single = true; return api; },
      single: function () { st.single = true; return api; },
      insert: function (row) { st.op = 'insert'; st.payload = row; return api; },
      upsert: function (row) { st.op = 'insert'; st.payload = row; return api; },
      update: function (row) { st.op = 'update'; st.payload = row; return api; },
      delete: function () { st.op = 'delete'; return api; },
      then: function (resolve, reject) { return exec().then(resolve, reject); },
      catch: function (f) { return exec().catch(f); },
    };
    return api;
  }

  /* ---------------- 实时同步:轮询代替 WebSocket ---------------- */
  var POLL_MS = 10000;
  function channel() {
    var handlers = [], timer = null, last = null, stopped = false;

    function tick() {
      if (stopped) return;
      req('GET', '/records/stamp').then(function (r) {
        if (!r.ok) return;
        var cur = r.body.n + '|' + r.body.t;
        if (last !== null && cur !== last) {
          handlers.forEach(function (h) {
            try { h({ eventType: 'UPDATE', new: {}, old: {}, table: 'records', schema: 'public' }); }
            catch (e) { console.error(e); }
          });
        }
        last = cur;
      });
    }

    var ch = {
      on: function (_evt, _filter, cb) { handlers.push(cb); return ch; },
      subscribe: function (cb) {
        tick();
        timer = setInterval(tick, POLL_MS);
        // 切回窗口时立刻查一次，不用等下一轮
        document.addEventListener('visibilitychange', function () {
          if (document.visibilityState === 'visible') tick();
        });
        if (cb) setTimeout(function () { cb('SUBSCRIBED'); }, 0);
        return ch;
      },
      unsubscribe: function () { stopped = true; if (timer) clearInterval(timer); return Promise.resolve('ok'); },
    };
    return ch;
  }

  /* ---------------- 对外:冒充 window.supabase ---------------- */
  window.supabase = {
    createClient: function () {
      return {
        auth: auth,
        from: builder,
        channel: channel,
        removeChannel: function (ch) { if (ch && ch.unsubscribe) ch.unsubscribe(); return Promise.resolve('ok'); },
        removeAllChannels: function () { return Promise.resolve('ok'); },
      };
    },
  };
  window.RUNADOPS_SELFHOSTED = true;
})();
