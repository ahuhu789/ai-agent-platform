let currentConversationId = null;
let isGenerating = false;

// DOM Elements
const chatMessagesEl = document.getElementById("chatMessages");
const chatInputEl = document.getElementById("chatInput");
const sendBtnEl = document.getElementById("sendBtn");
const conversationListEl = document.getElementById("conversationList");
const newChatBtn = document.getElementById("newChatBtn");
const settingsModal = document.getElementById("settingsModal");
const openSettingsBtn = document.getElementById("openSettingsBtn");
const closeSettingsBtn = document.getElementById("closeSettingsBtn");
const saveSettingsBtn = document.getElementById("saveSettingsBtn");

// Clean unnecessary backslash escapes from LLMs (\| -> |, \@ -> @, \* -> *, etc.)
function cleanMarkdownEscapes(text) {
  if (!text) return "";
  // 1. Unescape pipe: \| -> |
  let cleaned = text.replace(/\\\|/g, "|");
  // 2. Unescape at sign in emails: \@ -> @
  cleaned = cleaned.replace(/\\@/g, "@");
  // 3. Unescape markdown syntax if escaped: \* -> *, \_ -> _, \# -> #
  cleaned = cleaned.replace(/\\([\*_`~#\-+!])/g, "$1");
  // 4. Strip leading indentation before headers and table lines (so marked doesn't treat them as code blocks)
  cleaned = cleaned.replace(/^[ \t]+(#{1,6}\s)/gm, "$1");
  cleaned = cleaned.replace(/^[ \t]+(\|)/gm, "$1");
  return cleaned;
}

// Markdown parser helper with Marked.js + DOMPurify and robust fallback
function renderMarkdown(text) {
  if (!text) return "";

  // 1. Clean backslash escapes
  const cleaned = cleanMarkdownEscapes(text.trim());

  // 2. If marked is available, use it for standard GFM (GitHub Flavored Markdown)
  if (window.marked && typeof window.marked.parse === "function") {
    try {
      let rawHtml = window.marked.parse(cleaned, {
        gfm: true,
        breaks: true,
      });

      // Wrap tables inside responsive container for horizontal scroll on mobile/narrow screens
      rawHtml = rawHtml.replace(/<table(\s*[^>]*)>/gi, '<div class="table-responsive"><table class="data-table"$1>');
      rawHtml = rawHtml.replace(/<\/table>/gi, '</table></div>');

      // Sanitize with DOMPurify if available for 100% XSS security
      if (window.DOMPurify && typeof window.DOMPurify.sanitize === "function") {
        return window.DOMPurify.sanitize(rawHtml, {
          ADD_ATTR: ['target', 'align'],
        });
      }
      return rawHtml;
    } catch (e) {
      console.warn("Lỗi khi parse bằng marked, chuyển sang fallback parser:", e);
    }
  }

  // 3. Robust Fallback parser (handles tables, bold, italics, code, lists, headers)
  return fallbackRenderMarkdown(cleaned);
}

// Fallback lightweight parser when external libraries are not present
function fallbackRenderMarkdown(text) {
  const lines = text.split("\n");
  let inTable = false;
  let tableHeader = "";
  let tableRows = [];
  let out = [];

  function flushTable() {
    if (tableRows.length > 0 || tableHeader) {
      let tblHtml = '<div class="table-responsive"><table class="data-table">';
      if (tableHeader) tblHtml += `<thead>${tableHeader}</thead>`;
      if (tableRows.length > 0) tblHtml += `<tbody>${tableRows.join("")}</tbody>`;
      tblHtml += '</table></div>';
      out.push(tblHtml);
      tableHeader = "";
      tableRows = [];
    }
    inTable = false;
  }

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i].trim();

    // Table line
    if (line.startsWith("|")) {
      let trimmedLine = line;
      if (trimmedLine.endsWith("|")) {
        trimmedLine = trimmedLine.slice(1, -1);
      } else {
        trimmedLine = trimmedLine.slice(1);
      }
      const cells = trimmedLine.split("|").map(c => c.trim());
      // Check if separator line (|---|---|)
      if (cells.every(c => /^:?-+:?$/.test(c))) {
        continue;
      }
      if (!inTable) {
        inTable = true;
        tableHeader = `<tr>${cells.map(c => `<th>${inlineFormat(c)}</th>`).join("")}</tr>`;
      } else {
        tableRows.push(`<tr>${cells.map(c => `<td>${inlineFormat(c)}</td>`).join("")}</tr>`);
      }
      continue;
    } else if (inTable) {
      flushTable();
    }

    // Headers
    if (/^###\s+(.*)$/.test(line)) {
      out.push(`<h3>${inlineFormat(line.replace(/^###\s+/, ""))}</h3>`);
    } else if (/^##\s+(.*)$/.test(line)) {
      out.push(`<h2>${inlineFormat(line.replace(/^##\s+/, ""))}</h2>`);
    } else if (/^#\s+(.*)$/.test(line)) {
      out.push(`<h1>${inlineFormat(line.replace(/^#\s+/, ""))}</h1>`);
    } else if (/^[•\-\*]\s+(.*)$/.test(line)) {
      out.push(`<li>${inlineFormat(line.replace(/^[•\-\*]\s+/, ""))}</li>`);
    } else if (line.length > 0) {
      out.push(`<p>${inlineFormat(line)}</p>`);
    }
  }

  if (inTable) {
    flushTable();
  }

  let result = out.join("");
  result = result.replace(/(<li>.*?<\/li>)+/gs, "<ul>$&</ul>");
  return result;
}

function inlineFormat(text) {
  let s = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  s = s.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*(.*?)\*/g, "<em>$1</em>");
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  return s;
}

// Format date
function formatDate(dateStr) {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch (e) {
    return "";
  }
}

// Initialize Application
async function initApp() {
  loadSettings();
  await loadConversations();

  // Event Listeners
  newChatBtn.addEventListener("click", startNewChat);
  sendBtnEl.addEventListener("click", handleSendMessage);

  chatInputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  });

  chatInputEl.addEventListener("input", () => {
    chatInputEl.style.height = "auto";
    chatInputEl.style.height = Math.min(chatInputEl.scrollHeight, 120) + "px";
  });

  // Modal events
  openSettingsBtn.addEventListener("click", () => {
    settingsModal.style.display = "flex";
  });
  closeSettingsBtn.addEventListener("click", () => {
    settingsModal.style.display = "none";
  });
  saveSettingsBtn.addEventListener("click", saveSettings);

  // Quick chips
  document.querySelectorAll(".prompt-card").forEach((card) => {
    card.addEventListener("click", () => {
      const prompt = card.getAttribute("data-prompt");
      if (prompt) {
        chatInputEl.value = prompt;
        handleSendMessage();
      }
    });
  });
}

// Load Conversation List
async function loadConversations() {
  try {
    const res = await fetch("/conversations");
    if (!res.ok) return;
    const conversations = await res.json();
    renderConversationList(conversations);
  } catch (err) {
    console.error("Lỗi tải danh sách hội thoại:", err);
  }
}

function renderConversationList(conversations) {
  conversationListEl.innerHTML = "";
  if (!conversations || conversations.length === 0) {
    conversationListEl.innerHTML = '<div style="font-size:12px; color:#64748b; padding:12px;">Chưa có cuộc trò chuyện nào</div>';
    return;
  }

  conversations.forEach((conv) => {
    const item = document.createElement("div");
    item.className = `conversation-item ${conv.id === currentConversationId ? "active" : ""}`;
    item.innerHTML = `
      <div class="conv-title" title="${conv.title || 'Cuộc trò chuyện'}">💬 ${conv.title || 'Cuộc trò chuyện'}</div>
      <button class="conv-del-btn" title="Xóa hội thoại">✕</button>
    `;

    item.addEventListener("click", (e) => {
      if (e.target.classList.contains("conv-del-btn")) {
        deleteConversation(conv.id);
        return;
      }
      selectConversation(conv.id);
    });

    conversationListEl.appendChild(item);
  });
}

async function selectConversation(convId) {
  currentConversationId = convId;
  await loadConversations(); // refresh active highlight
  try {
    const res = await fetch(`/conversations/${convId}`);
    if (!res.ok) return;
    const data = await res.json();
    renderMessageHistory(data.messages || []);
  } catch (err) {
    console.error("Lỗi tải chi tiết cuộc hội thoại:", err);
  }
}

async function deleteConversation(convId) {
  if (!confirm("Bạn có chắc chắn muốn xóa cuộc trò chuyện này?")) return;
  try {
    await fetch(`/conversations/${convId}`, { method: "DELETE" });
    if (currentConversationId === convId) {
      startNewChat();
    } else {
      await loadConversations();
    }
  } catch (err) {
    console.error("Lỗi xóa hội thoại:", err);
  }
}

function startNewChat() {
  currentConversationId = null;
  loadConversations();
  chatMessagesEl.innerHTML = `
    <div class="welcome-box">
      <div class="welcome-icon">🤖</div>
      <h2 class="welcome-title">AI Agent Platform FME</h2>
      <p class="welcome-desc">
        Hệ thống Multi-Agent thông minh hỗ trợ hỏi đáp và tra cứu dữ liệu doanh nghiệp tự động qua giao thức MCP (Model Context Protocol).
      </p>
      <div class="quick-prompts">
        <div class="prompt-card" data-prompt="Có bao nhiêu ứng viên đang chờ phỏng vấn?">
          <span>💼</span>
          <span>Có bao nhiêu ứng viên đang chờ phỏng vấn?</span>
        </div>
        <div class="prompt-card" data-prompt="Danh sách vị trí đang tuyển là gì?">
          <span>📋</span>
          <span>Danh sách vị trí đang tuyển dụng là gì?</span>
        </div>
        <div class="prompt-card" data-prompt="Cho tôi thông tin ứng viên có mã UV001">
          <span>🔍</span>
          <span>Tra cứu thông tin ứng viên mã UV001</span>
        </div>
        <div class="prompt-card" data-prompt="Tổng hợp tình hình tuyển dụng tháng 8">
          <span>📊</span>
          <span>Báo cáo tổng hợp số liệu tuyển dụng tháng 8</span>
        </div>
      </div>
    </div>
  `;

  // re-bind quick prompts
  document.querySelectorAll(".prompt-card").forEach((card) => {
    card.addEventListener("click", () => {
      const prompt = card.getAttribute("data-prompt");
      if (prompt) {
        chatInputEl.value = prompt;
        handleSendMessage();
      }
    });
  });
}

function renderMessageHistory(messages) {
  chatMessagesEl.innerHTML = "";
  messages.forEach((msg) => {
    appendMessageToDOM(msg.role, msg.content, msg.metadata);
  });
  scrollToBottom();
}

function appendMessageToDOM(role, content, metadata = null) {
  // Clear welcome box on first message
  const welcomeBox = document.querySelector(".welcome-box");
  if (welcomeBox) welcomeBox.remove();

  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const wrapper = document.createElement("div");
  wrapper.className = "message-content-wrapper";

  // If assistant has multi-agent metadata, show routing trace badge
  if (role === "assistant" && metadata) {
    const traceContainer = document.createElement("div");
    traceContainer.className = "trace-badge-container";

    const routedBy = metadata.routed_by || "root_agent";
    const agent = metadata.agent || metadata.source || metadata.intent || "hiring";
    const latencyBadge = (metadata.latency_ms !== undefined) 
      ? `<span class="badge-arrow">➔</span><span class="trace-badge badge-latency" title="Thời gian phản hồi hệ thống">⚡ ${metadata.latency_ms}ms</span>` 
      : "";

    traceContainer.innerHTML = `
      <span class="trace-badge badge-root">🧭 ${routedBy}</span>
      <span class="badge-arrow">➔</span>
      <span class="trace-badge ${badgeClass}">🤖 ${agent}_agent</span>
      ${tool ? `<span class="badge-arrow">➔</span><span class="trace-badge badge-tool">⚙️ ${tool}</span>` : ""}
      ${latencyBadge}
    `;
    wrapper.appendChild(traceContainer);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = renderMarkdown(content);
  wrapper.appendChild(bubble);

  // If metadata exists, add toggleable debug inspector
  if (role === "assistant" && metadata && Object.keys(metadata).length > 0) {
    const metaToggle = document.createElement("div");
    metaToggle.className = "meta-toggle";
    metaToggle.innerHTML = "<span>ℹ️ Chi tiết kỹ thuật & payload</span>";

    const metaDetails = document.createElement("pre");
    metaDetails.className = "meta-details";
    metaDetails.textContent = JSON.stringify(metadata, null, 2);

    metaToggle.addEventListener("click", () => {
      const isVisible = metaDetails.style.display === "block";
      metaDetails.style.display = isVisible ? "none" : "block";
      metaToggle.innerHTML = isVisible
        ? "<span>ℹ️ Chi tiết kỹ thuật & payload</span>"
        : "<span>▲ Ẩn chi tiết kỹ thuật</span>";
    });

    wrapper.appendChild(metaToggle);
    wrapper.appendChild(metaDetails);
  }

  row.appendChild(wrapper);
  chatMessagesEl.appendChild(row);
  scrollToBottom();
}

function scrollToBottom() {
  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

// Handle Send Message
async function handleSendMessage() {
  const text = chatInputEl.value.trim();
  if (!text || isGenerating) return;

  chatInputEl.value = "";
  chatInputEl.style.height = "auto";
  isGenerating = true;
  sendBtnEl.disabled = true;

  // Append user message to DOM
  appendMessageToDOM("user", text);

  // Loading indicator bubble
  const loadingRow = document.createElement("div");
  loadingRow.className = "message-row assistant";
  loadingRow.id = "loadingMessage";
  loadingRow.innerHTML = `
    <div class="message-content-wrapper">
      <div class="bubble" style="color:#94a3b8; display:flex; align-items:center; gap:8px;">
        <span>⏳ Đang phân tích câu hỏi & truy vấn công cụ MCP...</span>
      </div>
    </div>
  `;
  chatMessagesEl.appendChild(loadingRow);
  scrollToBottom();

  try {
    const payload = {
      message: text,
      conversation_id: currentConversationId,
    };

    const startTime = performance.now();
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    const durationMs = Math.round(performance.now() - startTime);
    loadingRow.remove();

    if (!data.metadata) {
      data.metadata = {};
    }
    data.metadata.latency_ms = durationMs;

    if (data.conversation_id) {
      currentConversationId = data.conversation_id;
      loadConversations();
    }

    appendMessageToDOM("assistant", data.reply, data.metadata);
  } catch (err) {
    loadingRow.remove();
    appendMessageToDOM("assistant", `❌ Lỗi kết nối API: ${err.message}`);
  } finally {
    isGenerating = false;
    sendBtnEl.disabled = false;
    chatInputEl.focus();
  }
}

// Settings Modal Management
async function loadSettings() {
  const pEl = document.getElementById("settingProvider");
  const kEl = document.getElementById("settingApiKey");
  const mEl = document.getElementById("settingModel");
  const noticeEl = document.getElementById("apiKeyNotice");

  const PROVIDER_METADATA = {
    groq: {
      model: "openai/gpt-oss-120b",
      placeholder: "Dán Groq API Key (bắt đầu bằng gsk_...)",
    },
    openrouter: {
      model: "deepseek/deepseek-chat",
      placeholder: "Dán OpenRouter API Key (bắt đầu bằng sk-or-...)",
    },
    google: {
      model: "gemini-2.0-flash",
      placeholder: "Dán Google AI Studio API Key (bắt đầu bằng AIza...)",
    },
    deepseek: {
      model: "deepseek-chat",
      placeholder: "Dán DeepSeek API Key (bắt đầu bằng sk-...)",
    },
    qwen: {
      model: "qwen-plus",
      placeholder: "Dán DashScope / Qwen API Key (bắt đầu bằng sk-...)",
    },
    openai: {
      model: "gpt-4o-mini",
      placeholder: "Dán OpenAI API Key (bắt đầu bằng sk-...)",
    },
    ollama: {
      model: "llama3.2",
      placeholder: "Tùy chọn (để trống nếu chạy local)",
    },
  };

  // Listener to change model default based on selected provider
  if (pEl && mEl) {
    pEl.addEventListener("change", () => {
      const selected = pEl.value;
      if (PROVIDER_METADATA[selected]) {
        mEl.value = PROVIDER_METADATA[selected].model;
        if (kEl) kEl.placeholder = PROVIDER_METADATA[selected].placeholder;
      }
    });
  }

  // Auto-detect provider when user pastes or types an API Key
  if (kEl && pEl && mEl) {
    kEl.addEventListener("input", () => {
      const val = kEl.value.trim();
      let detected = null;
      if (val.startsWith("gsk_")) {
        detected = "groq";
      } else if (val.startsWith("sk-or-")) {
        detected = "openrouter";
      } else if (val.startsWith("AIza")) {
        detected = "google";
      }
      if (detected && detected !== pEl.value) {
        pEl.value = detected;
        if (PROVIDER_METADATA[detected]) {
          mEl.value = PROVIDER_METADATA[detected].model;
          kEl.placeholder = PROVIDER_METADATA[detected].placeholder;
        }
      }
    });
  }

  // Load from backend /settings API
  try {
    const res = await fetch("/settings");
    if (res.ok) {
      const data = await res.json();
      if (pEl && data.provider) pEl.value = data.provider;
      if (mEl && data.model) mEl.value = data.model;
      if (data.has_api_key && noticeEl) {
        noticeEl.style.display = "block";
        noticeEl.textContent = `✓ Đã cấu hình trong .env: ${data.masked_api_key}`;
        if (kEl) kEl.placeholder = `${data.masked_api_key} (nhập key mới để thay đổi)`;
      }
      return;
    }
  } catch (err) {
    console.warn("Không thể tải /settings từ server, dùng localStorage fallback:", err);
  }

  // LocalStorage fallback
  const provider = localStorage.getItem("llm_provider") || "groq";
  const apiKey = localStorage.getItem("llm_api_key") || "";
  const model = localStorage.getItem("llm_model") || "openai/gpt-oss-120b";

  if (pEl) pEl.value = provider;
  if (kEl && apiKey) kEl.value = apiKey;
  if (mEl) mEl.value = model;
}

async function saveSettings() {
  const pEl = document.getElementById("settingProvider");
  const kEl = document.getElementById("settingApiKey");
  const mEl = document.getElementById("settingModel");
  const statusMsgEl = document.getElementById("settingsStatusMsg");
  const noticeEl = document.getElementById("apiKeyNotice");

  const provider = pEl ? pEl.value : "groq";
  const apiKey = kEl ? kEl.value.trim() : "";
  const model = mEl ? mEl.value.trim() : "openai/gpt-oss-120b";

  saveSettingsBtn.disabled = true;
  const originalBtnText = saveSettingsBtn.innerHTML;
  saveSettingsBtn.innerHTML = "⏳ Đang tạo .env & kích hoạt...";

  if (statusMsgEl) {
    statusMsgEl.style.display = "none";
  }

  try {
    const res = await fetch("/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: provider,
        api_key: apiKey,
        model: model,
      }),
    });

    const data = await res.json();

    if (res.ok && data.success) {
      localStorage.setItem("llm_provider", data.provider);
      localStorage.setItem("llm_model", data.model);
      if (apiKey) localStorage.setItem("llm_api_key", apiKey);

      if (noticeEl && data.has_api_key) {
        noticeEl.style.display = "block";
        noticeEl.textContent = `✓ Đã cấu hình trong .env: ${data.masked_api_key}`;
        if (kEl) {
          kEl.value = "";
          kEl.placeholder = `${data.masked_api_key} (nhập key mới để thay đổi)`;
        }
      }

      if (statusMsgEl) {
        statusMsgEl.style.display = "block";
        statusMsgEl.style.backgroundColor = "rgba(16, 185, 129, 0.2)";
        statusMsgEl.style.border = "1px solid #10b981";
        statusMsgEl.style.color = "#34d399";
        statusMsgEl.innerHTML = `<strong>Thành công!</strong> Đã tạo file <code>.env</code> chuẩn (Provider: <code>${data.provider}</code>, Model: <code>${data.model}</code>).`;
      }

      setTimeout(() => {
        settingsModal.style.display = "none";
        if (statusMsgEl) statusMsgEl.style.display = "none";
      }, 1200);

    } else {
      const errDetail = data.detail || data.message || "Không thể lưu cấu hình";
      if (statusMsgEl) {
        statusMsgEl.style.display = "block";
        statusMsgEl.style.backgroundColor = "rgba(239, 68, 68, 0.2)";
        statusMsgEl.style.border = "1px solid #ef4444";
        statusMsgEl.style.color = "#f87171";
        statusMsgEl.textContent = `Lỗi: ${errDetail}`;
      } else {
        alert(`❌ Lỗi khi lưu cấu hình: ${errDetail}`);
      }
    }
  } catch (err) {
    if (statusMsgEl) {
      statusMsgEl.style.display = "block";
      statusMsgEl.style.backgroundColor = "rgba(239, 68, 68, 0.2)";
      statusMsgEl.style.border = "1px solid #ef4444";
      statusMsgEl.style.color = "#f87171";
      statusMsgEl.textContent = `Lỗi kết nối API: ${err.message}`;
    } else {
      alert(`❌ Lỗi kết nối API: ${err.message}`);
    }
  } finally {
    saveSettingsBtn.disabled = false;
    saveSettingsBtn.innerHTML = originalBtnText;
  }
}

// Run on page load
document.addEventListener("DOMContentLoaded", initApp);
