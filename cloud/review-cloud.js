/* ────────────────────────────────────────────────────────────────────────────
 * 词云词表审核清单 · 云服务接入
 *
 * 应用：徐汇物业课题成果站（wbapp_VPtKCSEAs0RVwIWRwLF3mX）
 * 模块：Auth（审核人身份） + Database（审核台账持久化）
 *
 * 接入前的问题：页面上的「标记删除」只存在内存变量 DEL 里，刷新即全丢，
 * 多人无法共用同一份清单，也没有任何审核留痕。
 * 接入后：标记写入云端台账 wordcloud_review_marks，
 *   · 所有人看到的是同一份清单（共享可读）
 *   · 每条记录留痕「谁、什么时候」
 *   · 只能撤回**本人**的标记（由 RLS 在服务端强制，前端判不掉）
 *   · 刷新 / 换设备 / 换浏览器，标记都还在
 *
 * 说明：Auth 只作用于本页。其余报告页是公开成果，不做登录限制。
 * ──────────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  var TABLE = 'wordcloud_review_marks';
  var BAR_ID = 'wccBar';

  /* ── 0. 前置检查：配置 + SDK ───────────────────────────────────────────── */
  var cfg = window.WC_CLOUD_CONFIG;
  if (!cfg || !cfg.endpoint || !cfg.publishableKey) {
    console.error('[Cloud] 缺少 cloud/cloud-config.js 中的 publicConfig，云功能不启用');
    return;
  }
  var NS = window.WorkBuddyCloud;
  if (!NS || typeof NS.createWorkBuddyCloud !== 'function') {
    mountFatal('云 SDK 未能加载（需要能访问 jsDelivr CDN）。本页仍可浏览词表，但审核标记无法保存到云端。');
    return;
  }

  /* 唯一的客户端实例，Auth / Database 共用 */
  var cloud = NS.createWorkBuddyCloud({
    endpoint: cfg.endpoint,
    publishableKey: cfg.publishableKey
  });

  /* ── 1. 状态 ───────────────────────────────────────────────────────────── */
  var state = {
    session: null,        // 当前会话
    uid: null,            // 当前用户 id（仅用于 UI 判定，权限由 RLS 决定）
    known: new Set(),     // 云端台账里的全部词（含他人）
    busied: false,        // 同步中
    queued: false,        // 同步期间又有新改动
    applying: false,      // 正在把云端状态回填到页面（避免自触发）
    pendingLoginOtp: null,
    pendingSignupOtp: null,
    pendingReset: null,
    modal: null
  };

  function uidOf(session) {
    var u = session && session.user;
    if (!u) return null;
    return u.id || u.userId || u.uid || u.sub || null;
  }

  /* ── 2. 小工具 ─────────────────────────────────────────────────────────── */
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function $(id) { return document.getElementById(id); }

  var toastTimer = null;
  function toast(msg) {
    var t = $('wccToast');
    if (!t) {
      t = el('div', 'wcc-toast'); t.id = 'wccToast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('on');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('on'); }, 2600);
  }

  function fmtTime(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    function p(n) { return n < 10 ? '0' + n : '' + n; }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
      + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function setMsg(node, text, kind) {
    if (!node) return;
    node.textContent = text || '';
    node.className = 'wcc-msg' + (kind ? ' ' + kind : '');
  }

  /* 统一的人话错误提示：区分网络 / 未登录 / 无权限 / 重复 */
  function humanError(err, fallback) {
    if (!err) return fallback;
    var code = err.code || err.status || '';
    var msg = err.message || '';
    if (code === '42501' || /permission denied/i.test(msg)) {
      return '没有权限执行该操作（该记录不属于当前账号）。';
    }
    if (code === '23505' || /duplicate key/i.test(msg)) {
      return '该词已在你名下标记过。';
    }
    if (code === '42P01' || /does not exist/i.test(msg)) {
      return '云端台账不存在，请联系管理员检查环境。';
    }
    if (/Failed to fetch|NetworkError|network/i.test(msg)) {
      return '网络异常，请稍后重试。';
    }
    if (typeof err.kind === 'string') {
      if (err.kind === 'unauthenticated' || err.kind === 'invalid_grant') {
        return '登录状态已失效，请重新登录。';
      }
      if (err.kind === 'network' || err.kind === 'backend-unavailable') {
        return '网络异常，请稍后重试。';
      }
    }
    return msg || fallback;
  }

  /* ── 3. 数据库：审核台账读写 ───────────────────────────────────────────── */
  function requireSignedIn() {
    if (!state.session) { openModal('login'); return false; }
    return true;
  }

  function loadMarks() {
    return cloud.database
      .from(TABLE)
      .select('id, word, decision, owner_id, created_at')
      .order('created_at', { ascending: false })
      .limit(500)
      .then(function (res) {
        if (res.error) throw res.error;
        var rows = res.data || [];
        state.known = new Set(rows.map(function (r) { return r.word; }));
        renderLedger(rows);
        return rows;
      });
  }

  function insertMark(word) {
    /* owner_id 由数据库 DEFAULT auth.uid() 填写，前端绝不传 */
    return cloud.database
      .from(TABLE)
      .insert({ word: word, decision: 'delete' })
      .select()
      .then(function (res) {
        if (res.error) throw res.error;
        state.known.add(word);
        return (res.data || [])[0] || null;
      });
  }

  function deleteMark(word) {
    /* RLS: USING(owner_id = auth.uid()) —— 只能删自己的；
       删到别人的记录时返回空数组（不是报错），必须当成「未撤回」处理 */
    return cloud.database
      .from(TABLE)
      .delete()
      .eq('word', word)
      .select()
      .then(function (res) {
        if (res.error) throw res.error;
        var removed = Array.isArray(res.data) ? res.data : [];
        if (removed.length === 0) return false;   // 他人标记 / 已不存在
        state.known.delete(word);
        return true;
      });
  }

  /* ── 4. 页面联动 ───────────────────────────────────────────────────────── */
  var pageHooked = false;

  function hookPage() {
    if (pageHooked) return;
    if (typeof window.refresh !== 'function' || typeof window.DEL === 'undefined') {
      return;   // 页面脚本还没跑，稍后重试
    }
    /* 页面里所有改动（点词条 / 清空）最后都会调 refresh()，包住它就接住了全部变更 */
    var origRefresh = window.refresh;
    window.refresh = function () {
      var r = origRefresh.apply(this, arguments);
      if (!state.applying) scheduleSync();
      return r;
    };

    /* 视图重绘会新建 DOM，需补一次 del 类（不回写云端） */
    ['renderAll', 'renderStreet'].forEach(function (name) {
      var orig = window[name];
      if (typeof orig !== 'function') return;
      window[name] = function () {
        var r = orig.apply(this, arguments);
        applyDelClasses();
        return r;
      };
    });

    /* 未登录时拦截点击：直接提示登录，**不做本地假保存** */
    document.addEventListener('click', function (e) {
      var chip = e.target && e.target.closest ? e.target.closest('.w') : null;
      if (chip && !state.session) {
        e.preventDefault();
        e.stopPropagation();
        toast('请先登录后再标记，标记会保存到云端审核台账');
        openModal('login');
        return;
      }
      var reset = e.target && e.target.id === 'btnReset';
      if (reset && state.session) {
        if (!window.confirm('将撤回「我」的全部标记（其他审核人的标记不受影响），继续？')) {
          e.stopPropagation();
          e.preventDefault();
          return;
        }
      }
      if (reset && !state.session) {
        e.stopPropagation();
        e.preventDefault();
        toast('未登录，没有可撤回的标记');
      }
    }, true);

    pageHooked = true;
  }

  function applyDelClasses() {
    var del = window.DEL || {};
    var nodes = document.querySelectorAll('.w');
    for (var i = 0; i < nodes.length; i++) {
      var w = nodes[i].getAttribute('data-w');
      nodes[i].classList.toggle('del', !!del[w]);
    }
  }

  /* 把云端台账回填到页面（不触发同步） */
  function applyMarksToPage() {
    if (typeof window.refresh !== 'function') return;
    state.applying = true;
    var d = {};
    state.known.forEach(function (w) { d[w] = 1; });
    window.DEL = d;
    window.refresh();
    state.applying = false;
  }

  function scheduleSync() {
    if (state.applying || !state.session) return;
    if (state.busied) { state.queued = true; return; }
    setTimeout(sync, 0);
  }

  /* 比对「页面上的标记」与「云端已知台账」，只把差量写回云端 */
  function sync() {
    if (state.applying || !state.session || state.busied) return;
    state.busied = true;

    var now = window.DEL || {};
    var added = [], removed = [];
    Object.keys(now).forEach(function (w) { if (!state.known.has(w)) added.push(w); });
    state.known.forEach(function (w) { if (!now[w]) removed.push(w); });

    var chain = Promise.resolve();
    var restored = [];

    added.forEach(function (w) {
      chain = chain.then(function () {
        return insertMark(w)
          .then(function () { setBar('syncing'); })
          .catch(function (err) {
            if (err && String(err.code) === '23505') { state.known.add(w); return; }
            /* 写失败 → 从界面撤回，避免「看起来存上了其实没有」 */
            delete window.DEL[w];
            restored.push(w);
            toast('「' + w + '」保存失败：' + humanError(err, '请稍后重试'));
          });
      });
    });

    removed.forEach(function (w) {
      chain = chain.then(function () {
        return deleteMark(w).then(function (ok) {
          if (!ok) {
            /* 该词由他人标记 —— 撤回无效，恢复显示并说明原因 */
            window.DEL[w] = 1;
            restored.push(w);
            toast('「' + w + '」由其他审核人标记，无法撤回');
          }
        }).catch(function (err) {
          window.DEL[w] = 1;
          restored.push(w);
          toast('「' + w + '」撤回失败：' + humanError(err, '请稍后重试'));
        });
      });
    });

    return chain.then(function () {
      state.busied = false;
      if (restored.length) applyMarksToPage();
      return refreshLedgerAndBar();
    }).catch(function (err) {
      state.busied = false;
      setBar('err', humanError(err, '同步失败'));
    }).then(function () {
      if (state.queued) { state.queued = false; sync(); }
    });
  }

  function refreshLedgerAndBar() {
    return loadMarks().then(function (rows) {
      setBar('ok', null, rows);
      return rows;
    }).catch(function (err) {
      setBar('err', humanError(err, '台账读取失败'));
    });
  }

  /* ── 5. 顶部状态条 + 台账明细 ─────────────────────────────────────────── */
  function setBar(kind, extra, rows) {
    var dot = $('wccDot'), stat = $('wccStat');
    if (!dot || !stat) return;
    dot.className = 'wcc-dot' + (kind === 'ok' ? ' on' : kind === 'err' ? ' err' : kind === 'syncing' ? '' : ' off');
    if (extra) { stat.textContent = extra; return; }
    if (!state.session) { stat.innerHTML = '未登录 · 标记不会保存'; return; }
    var list = rows;
    if (!list) {
      stat.innerHTML = '云端台账 <b>' + state.known.size + '</b> 条';
      return;
    }
    var mine = list.filter(function (r) { return state.uid && r.owner_id === state.uid; }).length;
    var others = list.length - mine;
    stat.innerHTML = '云端台账 <b>' + list.length + '</b> 条（我 <b>' + mine + '</b> 条 · 其他审核人 '
      + others + ' 条）';
    var sum = $('wccLedgerSum');
    if (sum) sum.textContent = '台账明细（' + list.length + ' 条）';
    renderLedgerRows(list);
  }

  function renderLedger(rows) {
    var sum = $('wccLedgerSum');
    if (sum) sum.textContent = '台账明细（' + rows.length + ' 条）';
    renderLedgerRows(rows);
  }

  function renderLedgerRows(rows) {
    var body = $('wccLedgerBody');
    if (!body) return;
    if (!rows.length) {
      body.innerHTML = '<div class="wcc-empty">台账还是空的 —— 点击下方任意词条即可标记为「建议删除」。</div>';
      return;
    }
    var html = '<table class="wcc-tbl"><thead><tr><th>词条</th><th>审核人</th><th>标记时间</th></tr></thead><tbody>';
    rows.forEach(function (r) {
      var mine = state.uid && r.owner_id === state.uid;
      html += '<tr><td>' + escapeHtml(r.word) + '</td>'
        + '<td class="' + (mine ? 'wcc-mine' : 'wcc-other') + '">' + (mine ? '我' : '其他审核人') + '</td>'
        + '<td>' + fmtTime(r.created_at) + '</td></tr>';
    });
    body.innerHTML = html + '</tbody></table>';
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function buildBar() {
    var bar = el('div', 'wcc-bar');
    bar.id = BAR_ID;
    var left = el('div', 'wcc-bar-l');
    var dot = el('span', 'wcc-dot'); dot.id = 'wccDot';
    left.appendChild(dot);
    left.appendChild(el('span', 'wcc-title', '审核台账（云端）'));
    var stat = el('span', 'wcc-stat'); stat.id = 'wccStat'; stat.textContent = '正在连接…';
    left.appendChild(stat);
    bar.appendChild(left);

    var right = el('div', 'wcc-bar-r');
    right.id = 'wccAuth';
    bar.appendChild(right);

    var host = document.querySelector('.hd') || document.body.firstElementChild;
    if (host && host.parentNode) host.parentNode.insertBefore(bar, host.nextSibling);
    else document.body.insertBefore(bar, document.body.firstChild);

    var led = el('details', 'wcc-ledger');
    led.id = 'wccLedger';
    var sm = el('summary'); sm.id = 'wccLedgerSum'; sm.textContent = '台账明细';
    led.appendChild(sm);
    var lb = el('div', 'wcc-ledger-body'); lb.id = 'wccLedgerBody';
    led.appendChild(lb);
    bar.parentNode.insertBefore(led, bar.nextSibling);
  }

  function renderAuthArea() {
    var box = $('wccAuth');
    if (!box) return;
    box.innerHTML = '';
    if (state.session) {
      var who = el('span', 'wcc-user', state.session.user && state.session.user.email
        ? state.session.user.email : '已登录');
      box.appendChild(who);
      var up = el('button', 'wcc-btn gh', '修改密码');
      up.type = 'button';
      up.addEventListener('click', openChangePassword);
      box.appendChild(up);
      var out = el('button', 'wcc-btn', '退出');
      out.type = 'button';
      out.addEventListener('click', doSignOut);
      box.appendChild(out);
    } else {
      var login = el('button', 'wcc-btn pri', '登录 / 注册');
      login.type = 'button';
      login.addEventListener('click', function () { openModal('login'); });
      box.appendChild(login);
      var hint = el('span', 'wcc-stat', '登录后才能保存审核标记');
      box.appendChild(hint);
    }
  }

  /* ── 6. 登录 / 注册弹窗 ───────────────────────────────────────────────── */
  function buildModal() {
    var wrap = el('div', 'wcc-modal');
    wrap.id = 'wccModal';
    wrap.hidden = true;

    var dlg = el('div', 'wcc-dlg');
    dlg.innerHTML = ''
      + '<button class="wcc-close" type="button" id="wccClose" aria-label="关闭">×</button>'
      + '<h3>审核人登录</h3>'
      + '<div class="wcc-sub">登录用于记录「谁标记了什么」。邮箱登录（本项目为 Web 应用，仅支持邮箱）。</div>'
      + '<div class="wcc-tabs">'
      + '  <button type="button" data-wcc-tab="login" class="on">登录</button>'
      + '  <button type="button" data-wcc-tab="signup">注册</button>'
      + '</div>'
      /* 登录 */
      + '<div id="wccPaneLogin">'
      + '  <div class="wcc-seg">'
      + '    <button type="button" data-wcc-mode="pwd" class="on">邮箱 + 密码</button>'
      + '    <button type="button" data-wcc-mode="otp">邮箱验证码</button>'
      + '  </div>'
      + '  <div id="wccPwdForm">'
      + '    <div class="wcc-field"><label>邮箱</label><input id="wccPwdEmail" type="email" autocomplete="username" placeholder="name@example.com"></div>'
      + '    <div class="wcc-field"><label>密码</label><input id="wccPwdPass" type="password" autocomplete="current-password" placeholder="请输入密码"></div>'
      + '    <div class="wcc-actions"><button class="wcc-btn pri" type="button" id="wccDoPwd">登录</button></div>'
      + '    <div style="margin-top:10px"><button class="wcc-link" type="button" id="wccForgot">忘记密码？</button></div>'
      + '  </div>'
      + '  <div id="wccOtpForm" hidden>'
      + '    <div class="wcc-field"><label>邮箱</label>'
      + '      <div class="wcc-with-btn"><input id="wccOtpEmail" type="email" autocomplete="username" placeholder="name@example.com">'
      + '      <button class="wcc-btn" type="button" id="wccSendLoginOtp">获取验证码</button></div></div>'
      + '    <div class="wcc-field"><label>验证码</label><input id="wccOtpCode" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="6 位验证码"></div>'
      + '    <div class="wcc-actions"><button class="wcc-btn pri" type="button" id="wccDoOtp">登录</button></div>'
      + '  </div>'
      + '</div>'
      /* 注册 */
      + '<div id="wccPaneSignup" hidden>'
      + '  <div class="wcc-field"><label>邮箱</label>'
      + '    <div class="wcc-with-btn"><input id="wccSuEmail" type="email" autocomplete="username" placeholder="name@example.com">'
      + '    <button class="wcc-btn" type="button" id="wccSendSignupOtp">获取验证码</button></div></div>'
      + '  <div class="wcc-field"><label>验证码</label><input id="wccSuCode" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="6 位验证码"></div>'
      + '  <div class="wcc-field"><label>设置密码</label><input id="wccSuPass" type="password" autocomplete="new-password" placeholder="至少 8 位，注册后可用于密码登录"></div>'
      + '  <div class="wcc-actions"><button class="wcc-btn pri" type="button" id="wccDoSignup">注册</button></div>'
      + '  <div class="wcc-foot">已有账号？切到「登录」页签即可。</div>'
      + '</div>'
      /* 重置密码 */
      + '<div id="wccPaneReset" hidden>'
      + '  <div class="wcc-field"><label>邮箱</label><input id="wccRsEmail" type="email" placeholder="name@example.com"></div>'
      + '  <div class="wcc-field"><label>验证码</label>'
      + '    <div class="wcc-with-btn"><input id="wccRsCode" type="text" inputmode="numeric" placeholder="邮箱收到的验证码">'
      + '    <button class="wcc-btn" type="button" id="wccSendResetOtp">获取验证码</button></div></div>'
      + '  <div class="wcc-field"><label>新密码</label><input id="wccRsPass" type="password" autocomplete="new-password" placeholder="至少 8 位"></div>'
      + '  <div class="wcc-actions"><button class="wcc-btn pri" type="button" id="wccDoReset">重置密码</button>'
      + '    <button class="wcc-btn" type="button" id="wccBackLogin">返回登录</button></div>'
      + '</div>'
      /* 修改密码（已登录） */
      + '<div id="wccPaneChange" hidden>'
      + '  <div class="wcc-field"><label>当前密码</label><input id="wccChOld" type="password" autocomplete="current-password"></div>'
      + '  <div class="wcc-field"><label>新密码</label><input id="wccChNew" type="password" autocomplete="new-password" placeholder="至少 8 位"></div>'
      + '  <div class="wcc-actions"><button class="wcc-btn pri" type="button" id="wccDoChange">保存</button></div>'
      + '</div>'
      + '<div class="wcc-msg" id="wccMsg"></div>'
      + '<div class="wcc-foot">审核标记保存在云端，刷新与换设备都不会丢。</div>';

    wrap.appendChild(dlg);
    document.body.appendChild(wrap);
    state.modal = wrap;
    bindModal();
  }

  function showPane(name) {
    ['Login', 'Signup', 'Reset', 'Change'].forEach(function (p) {
      var n = $('wccPane' + p);
      if (n) n.hidden = (p.toLowerCase() !== name.toLowerCase());
    });
    var tabs = document.querySelectorAll('.wcc-tabs button');
    for (var i = 0; i < tabs.length; i++) {
      var t = tabs[i].getAttribute('data-wcc-tab');
      tabs[i].classList.toggle('on', t === name.toLowerCase() && name !== 'reset' && name !== 'change');
      tabs[i].style.display = (name === 'reset' || name === 'change') ? 'none' : '';
    }
  }

  function openModal(pane) {
    if (!state.modal) buildModal();
    state.modal.hidden = false;
    showPane(pane === 'signup' ? 'signup' : 'login');
    setMsg($('wccMsg'), '');
  }

  function openChangePassword() {
    if (!state.session) return;
    if (!state.modal) buildModal();
    state.modal.hidden = false;
    showPane('change');
    setMsg($('wccMsg'), '');
  }

  function closeModal() { if (state.modal) state.modal.hidden = true; }

  function busy(btn, on, label) {
    if (!btn) return;
    btn.disabled = !!on;
    if (on) { btn.dataset.wccLabel = btn.textContent; btn.textContent = label || '处理中…'; }
    else if (btn.dataset.wccLabel) { btn.textContent = btn.dataset.wccLabel; }
  }

  function validEmail(v) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((v || '').trim()); }

  function bindModal() {
    $('wccClose').addEventListener('click', closeModal);
    state.modal.addEventListener('click', function (e) { if (e.target === state.modal) closeModal(); });

    var tabs = document.querySelectorAll('.wcc-tabs button');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].addEventListener('click', function () { showPane(this.getAttribute('data-wcc-tab')); });
    }
    var segs = document.querySelectorAll('.wcc-seg button');
    for (var j = 0; j < segs.length; j++) {
      segs[j].addEventListener('click', function () {
        var mode = this.getAttribute('data-wcc-mode');
        for (var k = 0; k < segs.length; k++) segs[k].classList.toggle('on', segs[k] === this);
        $('wccPwdForm').hidden = mode !== 'pwd';
        $('wccOtpForm').hidden = mode !== 'otp';
        setMsg($('wccMsg'), '');
      });
    }

    $('wccDoPwd').addEventListener('click', function () {
      var email = ($('wccPwdEmail').value || '').trim();
      var password = $('wccPwdPass').value || '';
      if (!validEmail(email)) return setMsg($('wccMsg'), '请输入正确的邮箱地址', 'err');
      if (!password) return setMsg($('wccMsg'), '请输入密码', 'err');
      var b = this; busy(b, true);
      cloud.auth.signInWithPassword({ email: email, password: password })
        .then(function (res) {
          if (res.error) { setMsg($('wccMsg'), humanLoginError(res.error), 'err'); return; }
          return afterSignIn(res.data);
        })
        .catch(function (err) { setMsg($('wccMsg'), humanError(err, '登录失败，请重试'), 'err'); })
        .then(function () { busy(b, false); });
    });

    $('wccSendLoginOtp').addEventListener('click', function () {
      var email = ($('wccOtpEmail').value || '').trim();
      if (!validEmail(email)) return setMsg($('wccMsg'), '请输入正确的邮箱地址', 'err');
      var b = this; busy(b, true, '发送中…');
      cloud.auth.sendOtp({ email: email })
        .then(function (res) {
          if (res.error) { setMsg($('wccMsg'), humanError(res.error, '验证码发送失败'), 'err'); return; }
          state.pendingLoginOtp = {
            email: email,
            verificationId: res.data.verificationId,
            isExistingUser: res.data.isExistingUser
          };
          setMsg($('wccMsg'), '验证码已发送到 ' + email + '，请查收（含垃圾邮件箱）', 'ok');
        })
        .catch(function (err) { setMsg($('wccMsg'), humanError(err, '验证码发送失败'), 'err'); })
        .then(function () { busy(b, false); });
    });

    $('wccDoOtp').addEventListener('click', function () {
      var email = ($('wccOtpEmail').value || '').trim();
      var token = ($('wccOtpCode').value || '').trim();
      var p = state.pendingLoginOtp;
      if (!token) return setMsg($('wccMsg'), '请输入验证码', 'err');
      if (!p || p.email !== email) {
        return setMsg($('wccMsg'), '请先为当前邮箱获取验证码', 'err');
      }
      var b = this; busy(b, true);
      /* 提交阶段绝不重新发码 */
      cloud.auth.verifyOtp({
        email: p.email,
        verificationId: p.verificationId,
        isExistingUser: p.isExistingUser,
        token: token
      }).then(function (res) {
        if (res.error) { setMsg($('wccMsg'), humanError(res.error, '验证码不正确或已过期'), 'err'); return; }
        state.pendingLoginOtp = null;
        return afterSignIn(res.data);
      }).catch(function (err) {
        setMsg($('wccMsg'), humanError(err, '登录失败，请重试'), 'err');
      }).then(function () { busy(b, false); });
    });

    $('wccSendSignupOtp').addEventListener('click', function () {
      var email = ($('wccSuEmail').value || '').trim();
      if (!validEmail(email)) return setMsg($('wccMsg'), '请输入正确的邮箱地址', 'err');
      var b = this; busy(b, true, '发送中…');
      cloud.auth.sendOtp({ email: email })
        .then(function (res) {
          if (res.error) { setMsg($('wccMsg'), humanError(res.error, '验证码发送失败'), 'err'); return; }
          state.pendingSignupOtp = {
            email: email,
            verificationId: res.data.verificationId,
            isExistingUser: res.data.isExistingUser
          };
          setMsg($('wccMsg'), res.data.isExistingUser
            ? '该邮箱已有账号，请直接用「登录」页签登录'
            : '验证码已发送，请设置密码后完成注册', res.data.isExistingUser ? '' : 'ok');
        })
        .catch(function (err) { setMsg($('wccMsg'), humanError(err, '验证码发送失败'), 'err'); })
        .then(function () { busy(b, false); });
    });

    $('wccDoSignup').addEventListener('click', function () {
      var email = ($('wccSuEmail').value || '').trim();
      var token = ($('wccSuCode').value || '').trim();
      var password = $('wccSuPass').value || '';
      var p = state.pendingSignupOtp;
      if (!token) return setMsg($('wccMsg'), '请输入验证码', 'err');
      if (!p || p.email !== email) return setMsg($('wccMsg'), '请先为当前邮箱获取验证码', 'err');
      if (p.isExistingUser) return setMsg($('wccMsg'), '该邮箱已注册，请切到「登录」页签', 'err');
      if (password.length < 8) return setMsg($('wccMsg'), '密码至少 8 位（注册后可用于密码登录）', 'err');
      var b = this; busy(b, true);
      cloud.auth.verifyOtp({
        email: p.email,
        verificationId: p.verificationId,
        isExistingUser: p.isExistingUser,
        token: token,
        password: password      /* 邮箱注册必须带密码，否则日后无法密码登录 */
      }).then(function (res) {
        if (res.error) { setMsg($('wccMsg'), humanError(res.error, '注册失败，请重试'), 'err'); return; }
        state.pendingSignupOtp = null;
        return afterSignIn(res.data);
      }).catch(function (err) {
        setMsg($('wccMsg'), humanError(err, '注册失败，请重试'), 'err');
      }).then(function () { busy(b, false); });
    });

    $('wccForgot').addEventListener('click', function () {
      if (!state.modal) buildModal();
      state.modal.hidden = false;
      showPane('reset');
      setMsg($('wccMsg'), '');
      var e = $('wccPwdEmail').value;
      if (e) $('wccRsEmail').value = e;
    });
    $('wccBackLogin').addEventListener('click', function () { showPane('login'); setMsg($('wccMsg'), ''); });

    $('wccSendResetOtp').addEventListener('click', function () {
      var email = ($('wccRsEmail').value || '').trim();
      if (!validEmail(email)) return setMsg($('wccMsg'), '请输入正确的邮箱地址', 'err');
      var b = this; busy(b, true, '发送中…');
      cloud.auth.resetPasswordForEmail(email)
        .then(function (res) {
          if (res.error) { setMsg($('wccMsg'), humanError(res.error, '验证码发送失败'), 'err'); return; }
          state.pendingReset = { email: email, handle: res.data };
          setMsg($('wccMsg'), '验证码已发送，请在下方填写验证码与新密码', 'ok');
        })
        .catch(function (err) { setMsg($('wccMsg'), humanError(err, '验证码发送失败'), 'err'); })
        .then(function () { busy(b, false); });
    });

    $('wccDoReset').addEventListener('click', function () {
      var email = ($('wccRsEmail').value || '').trim();
      var nonce = ($('wccRsCode').value || '').trim();
      var password = $('wccRsPass').value || '';
      var p = state.pendingReset;
      if (!p || p.email !== email) return setMsg($('wccMsg'), '请先为当前邮箱获取验证码', 'err');
      if (!nonce) return setMsg($('wccMsg'), '请输入验证码', 'err');
      if (password.length < 8) return setMsg($('wccMsg'), '新密码至少 8 位', 'err');
      var b = this; busy(b, true);
      p.handle.updateUser({ nonce: nonce, password: password })
        .then(function (res) {
          if (res.error) { setMsg($('wccMsg'), humanError(res.error, '重置失败，请重试'), 'err'); return; }
          state.pendingReset = null;
          return afterSignIn(res.data);
        })
        .catch(function (err) {
          setMsg($('wccMsg'), humanError(err, '重置失败，请重试'), 'err');
        }).then(function () { busy(b, false); });
    });

    $('wccDoChange').addEventListener('click', function () {
      var oldPassword = $('wccChOld').value || '';
      var newPassword = $('wccChNew').value || '';
      if (!oldPassword || newPassword.length < 8) {
        return setMsg($('wccMsg'), '请填写当前密码，且新密码至少 8 位', 'err');
      }
      var b = this; busy(b, true);
      cloud.auth.resetPasswordForOld({ oldPassword: oldPassword, newPassword: newPassword })
        .then(function (res) {
          if (res.error) { setMsg($('wccMsg'), humanError(res.error, '修改失败'), 'err'); return; }
          $('wccChOld').value = ''; $('wccChNew').value = '';
          setMsg($('wccMsg'), '密码已更新', 'ok');
        })
        .catch(function (err) { setMsg($('wccMsg'), humanError(err, '修改失败'), 'err'); })
        .then(function () { busy(b, false); });
    });
  }

  function humanLoginError(err) {
    if (err && (err.kind === 'unauthenticated' || err.kind === 'invalid_grant')) {
      return '账号或密码不正确';
    }
    return humanError(err, '登录失败，请重试');
  }

  /* ── 7. 会话生命周期 ───────────────────────────────────────────────────── */
  function afterSignIn(session) {
    state.session = session || null;
    state.uid = uidOf(session);
    closeModal();
    renderAuthArea();
    setBar('syncing', '正在读取云端台账…');
    return loadMarks()
      .then(function (rows) {
        applyMarksToPage();
        setBar('ok', null, rows);
        toast('已登录，审核标记将保存到云端');
      })
      .catch(function (err) {
        setBar('err', humanError(err, '台账读取失败'));
      });
  }

  function doSignOut() {
    cloud.auth.signOut().then(function (res) {
      if (res && res.error) { toast(humanError(res.error, '退出失败')); return; }
      state.session = null; state.uid = null;
      state.known = new Set();
      state.pendingLoginOtp = null; state.pendingSignupOtp = null;
      applyMarksToPage();
      renderAuthArea();
      setBar('off');
      renderLedger([]);
      toast('已退出，标记不再保存到云端');
    });
  }

  function handleSignedOut() {
    state.session = null; state.uid = null;
    state.known = new Set();
    if (pageHooked) applyMarksToPage();
    renderAuthArea();
    setBar('off');
    if (state.modal) closeModal();
  }

  /* ── 8. 启动 ───────────────────────────────────────────────────────────── */
  function boot() {
    buildBar();
    renderAuthArea();
    buildModal();
    hookPage();
    var retry = 0;
    (function waitPage() {
      if (pageHooked) return;
      if (retry++ > 40) return;
      setTimeout(function () { hookPage(); waitPage(); }, 50);
    })();

    if (typeof cloud.auth.onAuthStateChange === 'function') {
      cloud.auth.onAuthStateChange(function (event, session) {
        if (event === 'SIGNED_OUT') { handleSignedOut(); return; }
        if (session && !state.session) {
          state.session = session; state.uid = uidOf(session);
          renderAuthArea();
          loadMarks().then(function (rows) { applyMarksToPage(); setBar('ok', null, rows); })
            .catch(function (err) { setBar('err', humanError(err, '台账读取失败')); });
        }
      });
    }

    /* 已有会话则直接进入已登录态 */
    cloud.auth.getSession().then(function (res) {
      if (res && res.data) return afterSignInSilent(res.data);
      renderAuthArea();
      setBar('off');
    }).catch(function (err) {
      renderAuthArea();
      setBar('err', humanError(err, '会话读取失败'));
    });
  }

  function afterSignInSilent(session) {
    state.session = session;
    state.uid = uidOf(session);
    renderAuthArea();
    setBar('syncing', '正在读取云端台账…');
    return loadMarks().then(function (rows) {
      applyMarksToPage();
      setBar('ok', null, rows);
    }).catch(function (err) {
      setBar('err', humanError(err, '台账读取失败'));
    });
  }

  function mountFatal(msg) {
    try {
      var bar = el('div', 'wcc-bar');
      var dot = el('span', 'wcc-dot err');
      bar.appendChild(dot);
      var l = el('div', 'wcc-bar-l');
      l.appendChild(el('span', 'wcc-title', '审核台账（云端不可用）'));
      l.appendChild(el('span', 'wcc-stat', msg));
      bar.appendChild(l);
      var host = document.querySelector('.hd');
      if (host && host.parentNode) host.parentNode.insertBefore(bar, host.nextSibling);
      else document.body.insertBefore(bar, document.body.firstChild);
    } catch (e) { /* 提示失败不影响页面其它功能 */ }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
