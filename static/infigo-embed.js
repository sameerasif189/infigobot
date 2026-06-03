/**
 * Infigo Solutions — embeddable chat widget
 * Add before </body> on https://infigosolutions.com/ :
 *
 * <script
 *   src="https://YOUR-API.vercel.app/static/infigo-embed.js"
 *   data-api-url="https://YOUR-API.vercel.app"
 *   data-api-key="YOUR_PUBLIC_CHAT_API_KEY"
 *   defer></script>
 */
(function () {
  "use strict";

  var script = document.currentScript;
  if (!script) return;

  var API_URL = (script.getAttribute("data-api-url") || "").replace(/\/$/, "");
  var API_KEY = script.getAttribute("data-api-key") || "";
  var TITLE = script.getAttribute("data-title") || "Infigo Assistant";
  var COLOR = script.getAttribute("data-color") || "#6366f1";

  if (!API_URL) {
    console.warn("[infigo-embed] missing data-api-url");
    return;
  }

  var sessionKey = "infigo_chat_session";
  var visitorKey = "infigo_visitor";

  function loadVisitor() {
    try {
      return JSON.parse(localStorage.getItem(visitorKey) || "{}");
    } catch (e) {
      return {};
    }
  }

  function saveVisitor(v) {
    localStorage.setItem(visitorKey, JSON.stringify(v));
  }

  function parseNameEmail(text) {
    var m = text.match(/([^\s,]+@[^\s,]+)/);
    if (!m) return null;
    var email = m[1];
    var name = text.replace(email, "").replace(/[,;]/g, " ").trim();
    return { name: name || "Guest", email: email };
  }

  var style = document.createElement("style");
  style.textContent =
    "#infigo-chat-launcher{position:fixed;bottom:24px;right:24px;z-index:99999;width:56px;height:56px;border-radius:50%;border:none;background:" +
    COLOR +
    ";color:#fff;font-size:22px;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.25)}" +
    "#infigo-chat-panel{position:fixed;bottom:92px;right:24px;z-index:99999;width:min(380px,calc(100vw - 32px));height:480px;max-height:70vh;background:#0f172a;color:#f1f5f9;border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.4);display:none;flex-direction:column;font-family:system-ui,sans-serif;font-size:14px}" +
    "#infigo-chat-panel.open{display:flex}" +
    "#infigo-chat-head{padding:14px 16px;font-weight:600;border-bottom:1px solid rgba(148,163,184,.2)}" +
    "#infigo-chat-msgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px}" +
    ".infigo-msg{max-width:90%;padding:10px 12px;border-radius:12px;line-height:1.4}" +
    ".infigo-msg.user{align-self:flex-end;background:#334155}" +
    ".infigo-msg.bot{align-self:flex-start;background:#312e81}" +
    "#infigo-chat-input-row{display:flex;gap:8px;padding:12px;border-top:1px solid rgba(148,163,184,.2)}" +
    "#infigo-chat-input{flex:1;border-radius:8px;border:1px solid rgba(148,163,184,.3);background:#1e293b;color:#f1f5f9;padding:8px 10px}" +
    "#infigo-chat-send{border:none;border-radius:8px;background:" +
    COLOR +
    ";color:#fff;padding:8px 14px;cursor:pointer}" +
    ".infigo-book-btn{display:inline-block;margin-top:6px;color:#22d3ee;font-size:13px}";
  document.head.appendChild(style);

  var launcher = document.createElement("button");
  launcher.id = "infigo-chat-launcher";
  launcher.type = "button";
  launcher.setAttribute("aria-label", "Open chat");
  launcher.textContent = "💬";

  var panel = document.createElement("div");
  panel.id = "infigo-chat-panel";
  panel.innerHTML =
    '<div id="infigo-chat-head">' +
    TITLE +
    '</div><div id="infigo-chat-msgs"></div><div id="infigo-chat-input-row">' +
    '<input id="infigo-chat-input" type="text" placeholder="Ask about our services…" />' +
    '<button type="button" id="infigo-chat-send">Send</button></div>';

  document.body.appendChild(launcher);
  document.body.appendChild(panel);

  var msgs = document.getElementById("infigo-chat-msgs");
  var input = document.getElementById("infigo-chat-input");
  var sendBtn = document.getElementById("infigo-chat-send");

  function addMsg(role, text, extraHtml) {
    var el = document.createElement("div");
    el.className = "infigo-msg " + role;
    el.textContent = text;
    if (extraHtml) {
      var wrap = document.createElement("div");
      wrap.innerHTML = extraHtml;
      el.appendChild(wrap);
    }
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
  }

  launcher.addEventListener("click", function () {
    panel.classList.toggle("open");
    if (panel.classList.contains("open") && msgs.childElementCount === 0) {
      addMsg(
        "bot",
        "Hi! I can explain Infigo startup and enterprise services, our process, and how to book a call or request a proposal."
      );
    }
  });

  async function sendMessage() {
    var text = (input.value || "").trim();
    if (!text) return;
    input.value = "";
    sendBtn.disabled = true;
    addMsg("user", text);

    var visitor = loadVisitor();
    var parsed = parseNameEmail(text);
    if (parsed) {
      visitor = parsed;
      saveVisitor(visitor);
    }

    var headers = { "Content-Type": "application/json" };
    if (API_KEY) headers["X-Site-Api-Key"] = API_KEY;

    try {
      var res = await fetch(API_URL + "/chat/public", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({
          message: text,
          session_id: localStorage.getItem(sessionKey) || null,
          visitor_name: visitor.name || null,
          visitor_email: visitor.email || null,
          llm_mode: "api",
        }),
      });
      var data = await res.json();
      if (!res.ok) {
        addMsg("bot", data.detail || "Sorry, something went wrong.");
        return;
      }
      if (data.session_id) localStorage.setItem(sessionKey, data.session_id);
      var extra = "";
      if (data.booking_url) {
        extra =
          '<a class="infigo-book-btn" href="' +
          data.booking_url +
          '" target="_blank" rel="noopener">Book a meeting</a>';
      }
      addMsg("bot", data.answer || "", extra);
    } catch (e) {
      addMsg("bot", "Could not reach the assistant. Please try again or use our contact form.");
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") sendMessage();
  });
})();
