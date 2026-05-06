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
        msgWrapper.classList.add("d-flex", "flex-column", "mb-3", "message-wrapper");
        msgWrapper.style.alignItems = isSent ? "flex-end" : "flex-start";
        msgWrapper.id = `msg-${msg._id}`;

        const bubbleContainer = document.createElement("div");
        bubbleContainer.classList.add("d-flex", "align-items-center", "w-100");
        bubbleContainer.style.flexDirection = isSent ? "row-reverse" : "row";

        const bubble = document.createElement("div");
        bubble.classList.add("message-bubble", isSent ? "msg-sent" : "msg-received");
        bubble.innerText = msg.message;

        const actions = document.createElement("div");
        actions.classList.add("message-actions");

        if (isSent) {
            const deleteIcon = document.createElement("span");
            deleteIcon.classList.add("material-symbols-outlined", "action-icon");
            deleteIcon.innerText = "delete";
            deleteIcon.title = "Delete message";
            deleteIcon.onclick = () => deleteMessage(msg._id);
            actions.appendChild(deleteIcon);
        } else {
            const reactIcon = document.createElement("span");
            reactIcon.classList.add("material-symbols-outlined", "action-icon");
            reactIcon.innerText = "add_reaction";
            reactIcon.title = "React";
            reactIcon.onclick = () => toggleEmojiPicker(msg._id, reactIcon);
            actions.appendChild(reactIcon);
        }

        bubbleContainer.appendChild(bubble);
        bubbleContainer.appendChild(actions);

        const meta = document.createElement("div");
        meta.classList.add("msg-meta");
        meta.innerText = msg.timestamp;

        msgWrapper.appendChild(bubbleContainer);
        msgWrapper.appendChild(meta);

        // Render existing reactions
        if (msg.reactions && Object.keys(msg.reactions).length > 0) {
            const reactionList = document.createElement("div");
            reactionList.classList.add("d-flex", "gap-1", "mt-1");
            for (const [emoji, users] of Object.entries(msg.reactions)) {
                const badge = document.createElement("span");
                badge.classList.add("badge", "badge-light", "border", "rounded-pill");
                badge.innerText = `${emoji} ${users.length}`;
                reactionList.appendChild(badge);
            }
            msgWrapper.appendChild(reactionList);
        }

        if (prepend) {
            chatBox.prepend(msgWrapper);
        } else {
            chatBox.appendChild(msgWrapper);
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        lastMessageId = msg._id;
    }

    async function deleteMessage(msgId) {
        if (!confirm("Are you sure you want to delete this message?")) return;
        try {
            const res = await fetch(`/deletemsg?msg_id=${msgId}&ajax=true`);
            const data = await res.json();
            if (data.success) {
                document.getElementById(`msg-${msgId}`).remove();
            }
        } catch (e) {
            console.error("Delete failed", e);
        }
    }

    async function reactToMessage(msgId, emoji) {
        try {
            const res = await fetch("/api/message/react", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message_id: msgId, emoji: emoji })
            });
            const data = await res.json();
            if (data.success) {
                // For simplicity, just poll to refresh the message state
                pollMessages(true);
            }
        } catch (e) {
            console.error("Reaction failed", e);
        }
    }

    function toggleEmojiPicker(msgId, targetEl) {
        const emojis = ['👍', '❤️', '😂', '😮', '😢', '🔥'];
        const picker = document.createElement("div");
        picker.classList.add("card", "shadow", "p-2", "position-absolute");
        picker.style.zIndex = "1000";
        picker.style.bottom = "100%";

        emojis.forEach(e => {
            const btn = document.createElement("span");
            btn.innerText = e;
            btn.style.cursor = "pointer";
            btn.style.fontSize = "1.5rem";
            btn.classList.add("p-1");
            btn.onclick = () => {
                reactToMessage(msgId, e);
                picker.remove();
            };
            picker.appendChild(btn);
        });

        targetEl.parentElement.appendChild(picker);
        // Close picker when clicking outside
        setTimeout(() => {
            document.addEventListener('click', function closePicker(event) {
                if (!picker.contains(event.target)) {
                    picker.remove();
                    document.removeEventListener('click', closePicker);
                }
            }, { capture: true });
        }, 0);
    }

    async function pollMessages(force = false) {
        if (isPolling && !force) return;
        isPolling = true;
        try {
            const url = lastMessageId && !force
                ? `/api/messages?with=${encodeURIComponent(RECIPIENT)}&after=${lastMessageId}`
                : `/api/messages?with=${encodeURIComponent(RECIPIENT)}`;

            const res = await fetch(url);
            const messages = await res.json();

            if (Array.isArray(messages) && messages.length > 0) {
                if (force) chatBox.innerHTML = "";
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
