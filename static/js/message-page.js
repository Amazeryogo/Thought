document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    const chatBox = document.getElementById("chat-box");
    const chatInput = document.getElementById("chatInput");
    const chatForm = document.getElementById("chat-form");
    const statusText = document.getElementById("status-text");

    let oldestMessageId = null;

    socket.on('connect', () => {
        statusText.innerText = "Online";
        statusText.classList.remove('text-danger');
        socket.emit('join', {});
        // Mark messages as read when joining the room
        socket.emit('mark_read', { username: RECIPIENT });
    });

    socket.on('disconnect', () => {
        statusText.innerText = "Offline";
        statusText.classList.add('text-danger');
    });

    socket.on('new_message', (msg) => {
        if (msg.sender === RECIPIENT) {
            appendMessage(msg);
            socket.emit('mark_read', { username: RECIPIENT });
        }
    });

    socket.on('message_sent', (msg) => {
        appendMessage(msg);
    });

    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const message = chatInput.value.trim();
        if (message) {
            socket.emit('send_message', {
                recipient: RECIPIENT,
                message: message
            });
            chatInput.value = "";
        }
    });

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
    }

    async function loadInitialMessages() {
        try {
            const res = await fetch(`/api/messages?with=${encodeURIComponent(RECIPIENT)}`);
            const messages = await res.json();
            chatBox.innerHTML = "";
            messages.forEach(msg => appendMessage(msg));
            chatBox.scrollTop = chatBox.scrollHeight;
        } catch (e) {
            console.error("Failed to load messages", e);
        }
    }

    loadInitialMessages();
});
