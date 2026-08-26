(function () {
  const API_BASE = "";
  const BEARER_TOKEN = "xuhui-demo-2026";

  const chatArea = document.getElementById("chat-area");
  const input = document.getElementById("msg-input");
  const sendBtn = document.getElementById("send-btn");
  const quickBtns = document.querySelectorAll(".quick-btn");
  let isBusy = false;

  function setBusy(b) {
    isBusy = b;
    sendBtn.disabled = b;
    quickBtns.forEach(btn => { btn.disabled = b; btn.style.opacity = b ? 0.5 : 1; });
  }

  function getSessionId() {
    let sid = localStorage.getItem("xuhui_session_id");
    if (!sid) {
      sid = "s_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
      localStorage.setItem("xuhui_session_id", sid);
    }
    return sid;
  }

  function scrollToBottom() {
    setTimeout(() => {
      chatArea.scrollTop = chatArea.scrollHeight;
    }, 50);
  }

  function renderTable(table) {
    if (!table || !table.headers || !table.rows) return "";
    let html = '<table><thead><tr>';
    table.headers.forEach(h => { html += `<th>${h}</th>`; });
    html += '</tr></thead><tbody>';
    table.rows.forEach(row => {
      html += '<tr>';
      row.forEach(cell => {
        const cls = typeof cell === "number" ? 'num' : '';
        html += `<td class="${cls}">${cell}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    return html;
  }

  function addUserMessage(text) {
    const div = document.createElement("div");
    div.className = "message user";
    div.innerHTML = `<div class="bubble"></div>`;
    div.querySelector(".bubble").textContent = text;
    chatArea.appendChild(div);
    scrollToBottom();
  }

  function addLoadingMessage() {
    const div = document.createElement("div");
    div.className = "message assistant";
    div.id = "loading-msg";
    div.innerHTML = `<div class="bubble"><span class="loading"><span></span><span></span><span></span></span></div>`;
    chatArea.appendChild(div);
    scrollToBottom();
    return div;
  }

  function replaceLoading(loadingEl, reply, table) {
    const bubble = loadingEl.querySelector(".bubble");
    bubble.innerHTML = reply;
    if (table) {
      bubble.innerHTML += renderTable(table);
    }
    scrollToBottom();
  }

  async function sendMessage(text) {
    if (!text || !text.trim()) return;
    if (isBusy) return;
    addUserMessage(text.trim());
    input.value = "";
    setBusy(true);

    const loadingEl = addLoadingMessage();

    try {
      const resp = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${BEARER_TOKEN}`
        },
        body: JSON.stringify({
          message: text.trim(),
          session_id: getSessionId()
        })
      });

      let data = {};
      try { data = await resp.json(); } catch (_) { data = {}; }

      if (!resp.ok) {
        const statusText = {
          401: "鉴权失败:Token 无效或未配置",
          403: "访问被禁止",
          422: "请求参数错误",
          500: "服务器内部错误",
          502: "后端服务异常",
          503: "服务暂不可用",
        }[resp.status] || `HTTP 错误 ${resp.status}`;
        const detail = data && data.detail ? `（${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}）` : "";
        replaceLoading(loadingEl, `❌ ${statusText}${detail}\n\n请稍后重试，或联系管理员。`, null);
        return;
      }

      const reply = data && data.reply ? String(data.reply) : "（无回复内容）";
      replaceLoading(loadingEl, reply, data.table || null);
    } catch (err) {
      const msg = err && err.message ? err.message : String(err);
      replaceLoading(loadingEl, `❌ 网络连接失败\n\n${msg}\n\n请检查网络、服务是否启动（${window.location.origin}），或稍后重试。`, null);
    } finally {
      setBusy(false);
      setTimeout(() => input.focus(), 50);
    }
  }

  sendBtn.addEventListener("click", () => sendMessage(input.value));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input.value);
    }
  });

  quickBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const q = btn.getAttribute("data-q");
      sendMessage(q);
    });
  });

  input.focus();
})();
