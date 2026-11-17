const thread = document.querySelector("#thread");
const form = document.querySelector("#composer");
const message = document.querySelector("#message");
const suggestions = document.querySelector("#suggestions");
const tools = document.querySelector("#tools");
const services = document.querySelector("#services");

let sessionId = localStorage.getItem("northline-session") || "";

function addBubble(role, text) {
  const node = document.createElement("div");
  node.className = `bubble ${role}`;
  node.textContent = text;
  thread.appendChild(node);
  thread.scrollTop = thread.scrollHeight;
}

function showTools(calls) {
  tools.replaceChildren();
  if (!calls.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No tools on this reply.";
    tools.appendChild(empty);
    return;
  }
  for (const call of calls) {
    const block = document.createElement("div");
    block.className = "tool";
    const title = document.createElement("strong");
    title.textContent = call.name;
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify({ arguments: call.arguments, result: call.result }, null, 2);
    block.append(title, pre);
    tools.appendChild(block);
  }
}

async function send(text) {
  const body = text.trim();
  if (!body) return;
  addBubble("user", body);
  message.value = "";
  form.querySelector("button").disabled = true;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId || null, message: body }),
    });
    if (!response.ok) throw new Error(`request failed (${response.status})`);
    const data = await response.json();
    sessionId = data.session_id;
    localStorage.setItem("northline-session", sessionId);
    addBubble("assistant", data.reply);
    showTools(data.tool_calls || []);
  } catch (error) {
    addBubble("assistant", "The desk could not answer just now. Try again in a moment.");
    showTools([]);
  } finally {
    form.querySelector("button").disabled = false;
    message.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  send(message.value);
});

message.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

fetch("/api/meta")
  .then((response) => response.json())
  .then((meta) => {
    document.querySelector("#business-name").textContent = meta.business_name;
    document.querySelector("#disclaimer").textContent = meta.disclaimer;
    document.querySelector("#provider").textContent = `Model: ${meta.llm_provider}`;
    document.title = `${meta.business_name} — appointment desk`;
    for (const service of meta.services) {
      const item = document.createElement("li");
      item.textContent = `${service.name} · ${service.duration_min} min`;
      services.appendChild(item);
    }
    for (const prompt of meta.suggestions) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = prompt;
      button.addEventListener("click", () => send(prompt));
      suggestions.appendChild(button);
    }
    addBubble(
      "assistant",
      `${meta.business_name} can check a time, book a visit, or answer from the studio notes. ${meta.disclaimer}`,
    );
  });
