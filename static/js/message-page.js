  function md5(string) {
  return CryptoJS.MD5(string).toString();
}

const username = "{{ username }}";
const currentUser = "{{ current_user.username }}";
const chatBox = document.getElementById("chat-box");
const input = document.getElementById("chatInput");

function formatMessage(msg) {
  const messageDiv = document.createElement("div");
  messageDiv.classList.add("d-flex", "mb-3");
  if (msg.sender === currentUser) {
    messageDiv.classList.add("justify-content-end", "text-end");
  }

  const avatar = document.createElement("img");
  avatar.src = `/avatar/${msg.sender}`;
  avatar.alt = "avatar";
  avatar.classList.add("rounded-circle", "me-2");
  avatar.style.width = "40px";
  avatar.style.height = "40px";

  const messageContent = document.createElement("div");
  messageContent.classList.add("bg-light", "p-2", "rounded", "shadow-sm");
  messageContent.innerHTML = `
    <div class="fw-bold small">${msg.sender}</div>
    <div>${msg.message}</div>
  `;

  if (msg.sender === currentUser) {
    messageDiv.appendChild(messageContent);
    messageDiv.appendChild(avatar);
  } else {
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(messageContent);
  }

  return messageDiv;
}

async function fetchMessages() {
  try {
    const res = await fetch(`/messages6?with=${encodeURIComponent(username)}`);
    const data = await res.json();
    if (!Array.isArray(data)) throw new Error("Invalid data format");

    chatBox.innerHTML = "";
    data.forEach(msg => {
      chatBox.appendChild(formatMessage(msg));
    });
    chatBox.scrollTop = chatBox.scrollHeight;
  } catch (e) {
    console.error("Failed to load messages", e);
  }
}

async function sendMessage() {
  const content = input.value.trim();
  if (!content) return;

  const res = await fetch("/api/send_message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, message: content })
  });

  if (res.ok) {
    input.value = "";
    await fetchMessages();
  } else {
    alert("Failed to send message");
  }
}

fetchMessages();
setInterval(fetchMessages, 5000);