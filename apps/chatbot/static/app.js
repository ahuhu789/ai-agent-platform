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

// Markdown parser helper
function renderMarkdown(text) {
  if (!text) return "";
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Bold & Italics
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bullet points
  html = html.replace(/^[•\-\*]\s+(.*)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>");

  // Line breaks to paragraphs
  const paragraphs = html.split("\n\n");
  return paragraphs
    .map((p) => {
      p = p.trim();
      if (p.startsWith("<ul>") || p.startsWith("<li>")) return p;
      return `<p>${p.replace(/\n/g, "<br/>")}</p>`;
    })
    .join("");
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
    appendMessageToDOM(msg.role, msg.content);
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
    const tool = metadata.tool_used;
    const badgeClass = `badge-${agent}`;

    traceContainer.innerHTML = `
      <span class="trace-badge badge-root">🧭 ${routedBy}</span>
      <span class="badge-arrow">➔</span>
      <span class="trace-badge ${badgeClass}">🤖 ${agent}_agent</span>
      ${tool ? `<span class="badge-arrow">➔</span><span class="trace-badge badge-tool">⚙️ ${tool}</span>` : ""}
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

    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    loadingRow.remove();

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
function loadSettings() {
  const provider = localStorage.getItem("llm_provider") || "groq";
  const apiKey = localStorage.getItem("llm_api_key") || "";
  const model = localStorage.getItem("llm_model") || "openai/gpt-oss-120b";

  const pEl = document.getElementById("settingProvider");
  const kEl = document.getElementById("settingApiKey");
  const mEl = document.getElementById("settingModel");

  if (pEl) pEl.value = provider;
  if (kEl) kEl.value = apiKey;
  if (mEl) mEl.value = model;
}

function saveSettings() {
  const provider = document.getElementById("settingProvider").value;
  const apiKey = document.getElementById("settingApiKey").value;
  const model = document.getElementById("settingModel").value;

  localStorage.setItem("llm_provider", provider);
  localStorage.setItem("llm_api_key", apiKey);
  localStorage.setItem("llm_model", model);

  settingsModal.style.display = "none";
  alert("Đã lưu cấu hình LLM thành công!");
}

// Run on page load
document.addEventListener("DOMContentLoaded", initApp);
