document.addEventListener('DOMContentLoaded', () => {
    const chatBox = document.getElementById("chat-box");
    const chatInput = document.getElementById("chatInput");
    const chatForm = document.getElementById("chat-form");
    const statusText = document.getElementById("status-text");

    let lastMessageId = null;
    let isPolling = false;

    function appendMessage(msg, prepend = false) {
        const isSent = msg.sender === CURRENT_USER;
        const msgWrapper = document.createElement("div");
        msgWrapper.classList.add("d-flex", "flex-column", "mb-3");
        msgWrapper.style.alignItems = isSent ? "flex-end" : "flex-start";

        const bubble = document.createElement("div");
        bubble.classList.add("message-bubble", isSent ? "msg-sent" : "msg-received");
        bubble.innerText = msg.message;

        const meta = document.createElement("div");
        meta.classList.add("msg-meta");
        meta.innerText = msg.timestamp;

        msgWrapper.appendChild(bubble);
        msgWrapper.appendChild(meta);

        if (prepend) {
            chatBox.prepend(msgWrapper);
        } else {
            chatBox.appendChild(msgWrapper);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        lastMessageId = msg._id;
    }

    async function pollMessages() {
        if (isPolling) return;
        isPolling = true;
        try {
            const url = lastMessageId
                ? `/api/messages?with=${encodeURIComponent(RECIPIENT)}&after=${lastMessageId}`
                : `/api/messages?with=${encodeURIComponent(RECIPIENT)}`;

            const res = await fetch(url);
            const messages = await res.json();

            if (Array.isArray(messages) && messages.length > 0) {
                messages.forEach(msg => appendMessage(msg));
            }
            statusText.innerText = "Online";
        } catch (e) {
            console.error("Polling failed", e);
            statusText.innerText = "Connection lost...";
        } finally {
            isPolling = false;
        }
    }

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = chatInput.value.trim();
        if (!message) return;

        chatInput.value = "";
        try {
            const res = await fetch("/api/messages/send", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ recipient: RECIPIENT, message: message })
            });
            const data = await res.json();
            if (data.success) {
                appendMessage(data.message);
            }
        } catch (e) {
            console.error("Send failed", e);
        }
    });

    pollMessages();
    setInterval(pollMessages, 3000);
});
