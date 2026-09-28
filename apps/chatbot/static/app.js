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

// OCR State & Elements
let currentChatAttachment = null; // { file, filename, text, metadata }
let currentOcrModalResult = null; // { filename, text, metadata }

const openOcrModalBtn = document.getElementById("openOcrModalBtn");
const closeOcrBtn = document.getElementById("closeOcrBtn");
const ocrModal = document.getElementById("ocrModal");
const welcomeOcrCard = document.getElementById("welcomeOcrCard");
const chatAttachBtn = document.getElementById("chatAttachBtn");
const chatFileInput = document.getElementById("chatFileInput");
const chatAttachmentPreview = document.getElementById("chatAttachmentPreview");
const attachmentNameEl = document.getElementById("attachmentName");
const attachmentOcrStatusEl = document.getElementById("attachmentOcrStatus");
const attachmentThumbEl = document.getElementById("attachmentThumb");
const removeAttachmentBtn = document.getElementById("removeAttachmentBtn");

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
function initApp() {
  // Bind all UI listeners synchronously first
  setupAllEventListeners();

  // Then fetch initial server data asynchronously without blocking UI interactions
  loadSettings();
  loadConversations();
}

function setupAllEventListeners() {
  // Event Listeners
  if (newChatBtn) newChatBtn.addEventListener("click", startNewChat);
  if (sendBtnEl) sendBtnEl.addEventListener("click", handleSendMessage);

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

  // OCR Modal events
  if (openOcrModalBtn) openOcrModalBtn.addEventListener("click", openOcrModal);
  if (closeOcrBtn) closeOcrBtn.addEventListener("click", closeOcrModal);
  if (welcomeOcrCard) welcomeOcrCard.addEventListener("click", openOcrModal);

  // Close modals on clicking backdrop
  window.addEventListener("click", (e) => {
    if (e.target === settingsModal) settingsModal.style.display = "none";
    if (e.target === ocrModal) closeOcrModal();
  });

  // OCR Dropzone & Modal File Input
  const ocrDropZone = document.getElementById("ocrDropZone");
  const ocrModalFileInput = document.getElementById("ocrModalFileInput");
  if (ocrDropZone && ocrModalFileInput) {
    ocrDropZone.addEventListener("click", () => ocrModalFileInput.click());
    ocrModalFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        handleOcrModalFileUpload(e.target.files[0]);
      }
    });

    ocrDropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      ocrDropZone.classList.add("dragover");
    });
    ocrDropZone.addEventListener("dragleave", () => {
      ocrDropZone.classList.remove("dragover");
    });
    ocrDropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      ocrDropZone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleOcrModalFileUpload(e.dataTransfer.files[0]);
      }
    });
  }

  // OCR Modal Action Buttons
  const ocrCopyBtn = document.getElementById("ocrCopyBtn");
  const ocrDownloadBtn = document.getElementById("ocrDownloadBtn");
  const ocrSendToChatBtn = document.getElementById("ocrSendToChatBtn");
  const ocrResetBtn = document.getElementById("ocrResetBtn");

  if (ocrCopyBtn) ocrCopyBtn.addEventListener("click", copyOcrText);
  if (ocrDownloadBtn) ocrDownloadBtn.addEventListener("click", downloadOcrText);
  if (ocrSendToChatBtn) ocrSendToChatBtn.addEventListener("click", sendOcrTextToChat);
  if (ocrResetBtn) ocrResetBtn.addEventListener("click", resetOcrModal);

  // In-Chat Attachment Events
  if (chatAttachBtn && chatFileInput) {
    chatAttachBtn.addEventListener("click", () => chatFileInput.click());
    chatFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        handleChatFileAttachment(e.target.files[0]);
      }
    });
  }
  if (removeAttachmentBtn) {
    removeAttachmentBtn.addEventListener("click", clearChatAttachment);
  }

  // Global Drag & Drop onto Chat Area
  const chatMessagesEl = document.getElementById("chatMessages");
  const chatInputWrapper = document.querySelector(".chat-input-wrapper");
  [chatMessagesEl, chatInputWrapper].forEach((targetEl) => {
    if (!targetEl) return;
    targetEl.addEventListener("dragover", (e) => {
      e.preventDefault();
    });
    targetEl.addEventListener("drop", (e) => {
      e.preventDefault();
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        const file = e.dataTransfer.files[0];
        const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
        if (file.type.startsWith("image/") || isPdf) {
          handleChatFileAttachment(file);
        }
      }
    });
  });

  // Global Clipboard Paste (Ctrl+V) for Screenshots / Images
  window.addEventListener("paste", (e) => {
    if (e.clipboardData && e.clipboardData.items) {
      for (let i = 0; i < e.clipboardData.items.length; i++) {
        const item = e.clipboardData.items[i];
        if (item.type.indexOf("image") !== -1) {
          const blob = item.getAsFile();
          if (blob) {
            const pasteFile = new File([blob], `screenshot_${Date.now()}.png`, { type: blob.type });
            handleChatFileAttachment(pasteFile);
            break;
          }
        }
      }
    }
  });

  // Quick chips
  document.querySelectorAll(".prompt-card").forEach((card) => {
    card.addEventListener("click", () => {
      if (card.id === "welcomeOcrCard") return;
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
  if (!text && !currentChatAttachment) return;
  if (isGenerating) return;

  chatInputEl.value = "";
  chatInputEl.style.height = "auto";
  isGenerating = true;
  sendBtnEl.disabled = true;

  let messageToSend = text;
  let displayMessage = text;

  // If user attached an image with OCR text
  if (currentChatAttachment) {
    const ocrSnippet = currentChatAttachment.text ? currentChatAttachment.text.trim() : "";
    const fileName = currentChatAttachment.filename || "hình ảnh";

    if (ocrSnippet) {
      if (!text) {
        messageToSend = `[Văn bản trích xuất từ tệp ảnh ${fileName} qua OCR]:\n${ocrSnippet}\n\nHãy tóm tắt và phân tích nội dung tài liệu trên.`;
        displayMessage = `📎 **[Đã đính kèm ảnh: \`${fileName}\`]**\n\n*(Nội dung OCR nhận diện được: ${ocrSnippet.length} ký tự)*\n\nHãy tóm tắt và phân tích nội dung tài liệu trên.`;
      } else {
        messageToSend = `[Văn bản trích xuất từ tệp ảnh ${fileName} qua OCR]:\n${ocrSnippet}\n\n${text}`;
        displayMessage = `📎 **[Đã đính kèm ảnh: \`${fileName}\`]**\n\n${text}`;
      }
    } else {
      if (!text) {
        displayMessage = `📎 **[Đã đính kèm ảnh: \`${fileName}\`]**`;
      }
    }
    clearChatAttachment();
  }

  // Append user message to DOM
  appendMessageToDOM("user", displayMessage);

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
      message: messageToSend,
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

// =============================================================================
// OCR Functions & Handlers
// =============================================================================

function openOcrModal() {
  if (ocrModal) {
    ocrModal.style.display = "flex";
  }
}

function closeOcrModal() {
  if (ocrModal) {
    ocrModal.style.display = "none";
  }
}

function resetOcrModal() {
  const dropZone = document.getElementById("ocrDropZone");
  const loading = document.getElementById("ocrLoadingState");
  const resultContainer = document.getElementById("ocrResultContainer");
  const modalFileInput = document.getElementById("ocrModalFileInput");
  const copyBtn = document.getElementById("ocrCopyBtn");
  const downloadBtn = document.getElementById("ocrDownloadBtn");
  const sendChatBtn = document.getElementById("ocrSendToChatBtn");
  const resetBtn = document.getElementById("ocrResetBtn");

  if (dropZone) dropZone.style.display = "block";
  if (loading) loading.style.display = "none";
  if (resultContainer) resultContainer.style.display = "none";
  if (modalFileInput) modalFileInput.value = "";
  if (copyBtn) copyBtn.style.display = "none";
  if (downloadBtn) downloadBtn.style.display = "none";
  if (sendChatBtn) sendChatBtn.style.display = "none";
  if (resetBtn) resetBtn.style.display = "none";
  const pdfPlaceholder = document.getElementById("ocrPdfPlaceholder");
  if (pdfPlaceholder) pdfPlaceholder.style.display = "none";
  const previewImg = document.getElementById("ocrPreviewImage");
  if (previewImg) previewImg.style.display = "block";
  currentOcrModalResult = null;
}

async function runOcrApi(file, lang = "vie+eng", preprocess = true) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("lang", lang);
  formData.append("preprocess", preprocess ? "true" : "false");

  const res = await fetch("/ocr/process", {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || errData.error_message || `HTTP ${res.status}`);
  }
  return await res.json();
}

async function handleOcrModalFileUpload(file) {
  if (!file) return;
  const dropZone = document.getElementById("ocrDropZone");
  const loading = document.getElementById("ocrLoadingState");
  const resultContainer = document.getElementById("ocrResultContainer");
  const previewImg = document.getElementById("ocrPreviewImage");
  const extractedTextarea = document.getElementById("ocrExtractedText");
  const langSelect = document.getElementById("ocrLangSelect");
  const preprocessCheck = document.getElementById("ocrPreprocessCheck");
  const copyBtn = document.getElementById("ocrCopyBtn");
  const downloadBtn = document.getElementById("ocrDownloadBtn");
  const sendChatBtn = document.getElementById("ocrSendToChatBtn");
  const resetBtn = document.getElementById("ocrResetBtn");

  const lang = langSelect ? langSelect.value : "vie+eng";
  const preprocess = preprocessCheck ? preprocessCheck.checked : true;

  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  const isImage = file.type.startsWith("image/") || file.name.match(/\.(png|jpe?g|webp|bmp|tiff?)$/i);
  if (!isPdf && !isImage) {
    alert("Vui lòng chọn tệp hình ảnh (PNG, JPG, WEBP, BMP, TIFF) hoặc tài liệu PDF hợp lệ.");
    return;
  }

  if (dropZone) dropZone.style.display = "none";
  if (loading) loading.style.display = "flex";
  if (resultContainer) resultContainer.style.display = "none";

  // PDF or Image preview handling
  let pdfPlaceholder = document.getElementById("ocrPdfPlaceholder");
  if (isPdf) {
    if (previewImg) previewImg.style.display = "none";
    if (!pdfPlaceholder && previewImg && previewImg.parentNode) {
      pdfPlaceholder = document.createElement("div");
      pdfPlaceholder.id = "ocrPdfPlaceholder";
      pdfPlaceholder.style.cssText = "display:flex; flex-direction:column; align-items:center; justify-content:center; padding:35px 15px; color:#38bdf8; text-align:center;";
      pdfPlaceholder.innerHTML = `
        <span style="font-size:52px; line-height:1;">📄</span>
        <span style="font-size:13px; font-weight:600; margin-top:10px; color:#f1f5f9; word-break:break-all;">${file.name}</span>
        <span style="font-size:11px; color:#94a3b8; margin-top:4px;">Tài liệu PDF (${(file.size / 1024).toFixed(1)} KB)</span>
      `;
      previewImg.parentNode.appendChild(pdfPlaceholder);
    } else if (pdfPlaceholder) {
      pdfPlaceholder.style.display = "flex";
      pdfPlaceholder.innerHTML = `
        <span style="font-size:52px; line-height:1;">📄</span>
        <span style="font-size:13px; font-weight:600; margin-top:10px; color:#f1f5f9; word-break:break-all;">${file.name}</span>
        <span style="font-size:11px; color:#94a3b8; margin-top:4px;">Tài liệu PDF (${(file.size / 1024).toFixed(1)} KB)</span>
      `;
    }
  } else {
    if (pdfPlaceholder) pdfPlaceholder.style.display = "none";
    if (previewImg) {
      previewImg.style.display = "block";
      const imageUrl = URL.createObjectURL(file);
      previewImg.src = imageUrl;
    }
  }

  try {
    const result = await runOcrApi(file, lang, preprocess);
    loading.style.display = "none";
    resultContainer.style.display = "block";

    const text = result.text || "";
    if (extractedTextarea) extractedTextarea.value = text;

    const meta = result.metadata || {};
    const metricDuration = document.getElementById("metricDuration");
    const metricConfidence = document.getElementById("metricConfidence");
    const metricWords = document.getElementById("metricWords");
    const metricSize = document.getElementById("metricSize");

    if (metricDuration) metricDuration.innerHTML = `⚡ Thời gian: <span>${meta.duration_ms || 0} ms</span>`;
    if (metricConfidence) metricConfidence.innerHTML = `🎯 Độ tự tin: <span>${meta.confidence !== undefined ? Math.round(meta.confidence) : 100}%</span>`;
    if (metricWords) metricWords.innerHTML = `📝 Số từ: <span>${meta.word_count || 0} từ</span>`;
    if (metricSize) metricSize.innerHTML = `📏 Kích thước: <span>${meta.image_width || 0} x ${meta.image_height || 0}</span>`;

    if (copyBtn) copyBtn.style.display = "inline-flex";
    if (downloadBtn) downloadBtn.style.display = "inline-flex";
    if (sendChatBtn) sendChatBtn.style.display = "inline-flex";
    if (resetBtn) resetBtn.style.display = "inline-flex";

    currentOcrModalResult = {
      filename: file.name,
      text: text,
      metadata: meta,
    };
  } catch (err) {
    loading.style.display = "none";
    dropZone.style.display = "block";
    alert(`❌ Lỗi nhận diện OCR: ${err.message}`);
  }
}

function copyOcrText() {
  const textarea = document.getElementById("ocrExtractedText");
  if (!textarea || !textarea.value) return;
  navigator.clipboard.writeText(textarea.value).then(() => {
    const copyBtn = document.getElementById("ocrCopyBtn");
    if (copyBtn) {
      const orig = copyBtn.innerHTML;
      copyBtn.innerHTML = "✅ Đã sao chép!";
      setTimeout(() => { copyBtn.innerHTML = orig; }, 1500);
    }
  });
}

function downloadOcrText() {
  const textarea = document.getElementById("ocrExtractedText");
  if (!textarea || !textarea.value) return;
  const blob = new Blob([textarea.value], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `ocr_result_${Date.now()}.txt`;
  a.click();
}

function sendOcrTextToChat() {
  const textarea = document.getElementById("ocrExtractedText");
  if (!textarea || !textarea.value) return;
  const text = textarea.value.trim();
  closeOcrModal();
  chatInputEl.value = `[Dữ liệu tài liệu/hình ảnh đã quét qua OCR]:\n${text}\n\nHãy phân tích và tóm tắt nội dung trên.`;
  chatInputEl.style.height = "auto";
  chatInputEl.style.height = Math.min(chatInputEl.scrollHeight, 120) + "px";
  chatInputEl.focus();
}

// In-chat file attachment handling
async function handleChatFileAttachment(file) {
  if (!file) return;
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  const isImage = file.type.startsWith("image/") || file.name.match(/\.(png|jpe?g|webp|bmp|tiff?)$/i);
  if (!isPdf && !isImage) {
    alert("Vui lòng chọn tệp hình ảnh hợp lệ (PNG, JPG, WEBP, BMP, TIFF) hoặc tài liệu PDF để thực hiện OCR.");
    return;
  }

  if (chatAttachmentPreview) chatAttachmentPreview.style.display = "flex";
  if (attachmentNameEl) attachmentNameEl.textContent = file.name;
  if (attachmentOcrStatusEl) {
    attachmentOcrStatusEl.textContent = isPdf ? "⏳ Đang trích xuất & quét OCR PDF..." : "⏳ Đang quét OCR qua Tesseract...";
    attachmentOcrStatusEl.style.color = "#38bdf8";
  }

  // Generate thumbnail
  if (attachmentThumbEl) {
    if (isPdf) {
      attachmentThumbEl.innerHTML = `<span style="font-size:20px; line-height:1;">📄</span>`;
    } else {
      const objUrl = URL.createObjectURL(file);
      attachmentThumbEl.innerHTML = `<img src="${objUrl}" style="width:24px; height:24px; object-fit:cover; border-radius:4px;">`;
    }
  }

  currentChatAttachment = {
    file: file,
    filename: file.name,
    text: "",
    metadata: null,
  };

  try {
    const result = await runOcrApi(file, "vie+eng", true);
    if (result.success && result.text) {
      currentChatAttachment.text = result.text.trim();
      currentChatAttachment.metadata = result.metadata;
      const count = result.metadata ? result.metadata.word_count : (result.text.split(/\s+/).length);
      const typeLabel = isPdf ? "PDF" : "OCR";
      if (attachmentOcrStatusEl) {
        attachmentOcrStatusEl.textContent = `✅ Đã quét ${typeLabel} (${count} từ - ${result.metadata ? Math.round(result.metadata.confidence) : 100}%)`;
        attachmentOcrStatusEl.style.color = "#34d399";
      }
    } else {
      if (attachmentOcrStatusEl) {
        attachmentOcrStatusEl.textContent = isPdf ? "⚠️ PDF không chứa văn bản trích xuất được" : "⚠️ Ảnh không chứa văn bản rõ ràng";
        attachmentOcrStatusEl.style.color = "#fbbf24";
      }
    }
  } catch (err) {
    if (attachmentOcrStatusEl) {
      attachmentOcrStatusEl.textContent = `❌ Lỗi: ${err.message}`;
      attachmentOcrStatusEl.style.color = "#f87171";
    }
  }
}

function clearChatAttachment() {
  currentChatAttachment = null;
  if (chatAttachmentPreview) chatAttachmentPreview.style.display = "none";
  if (chatFileInput) chatFileInput.value = "";
}

// Global window helpers for inline HTML event handlers & programmatic access
window.openOcrModal = openOcrModal;
window.closeOcrModal = closeOcrModal;
window.resetOcrModal = resetOcrModal;
window.copyOcrText = copyOcrText;
window.downloadOcrText = downloadOcrText;
window.sendOcrTextToChat = sendOcrTextToChat;
window.clearChatAttachment = clearChatAttachment;

window.handleChatFileInputChange = function (inputEl) {
  if (inputEl && inputEl.files && inputEl.files[0]) {
    const file = inputEl.files[0];
    inputEl.value = "";
    handleChatFileAttachment(file);
  }
};

window.handleOcrModalFileInputChange = function (inputEl) {
  if (inputEl && inputEl.files && inputEl.files[0]) {
    const file = inputEl.files[0];
    inputEl.value = "";
    handleOcrModalFileUpload(file);
  }
};

// Run on page load
document.addEventListener("DOMContentLoaded", initApp);

