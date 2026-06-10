function confirmDelete() {
    return confirm("Are you sure you want to delete this post?");
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".like-btn").forEach(button => {
        button.addEventListener("click", () => {
            const postId = button.getAttribute("data-id");

            fetch(`/like?post_id=${postId}`, { method: "POST" })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    document.getElementById(`like-count-${postId}`).textContent = data.likes;
                    document.getElementById(`dislike-count-${postId}`).textContent = data.dislikes;
                } else {
                    alert(data.message || "Failed to like post");
                }
            })
            .catch(err => {
                console.error("Error:", err);
                alert("An error occurred while liking the post.");
            });
        });
    });

    document.querySelectorAll(".dislike-btn").forEach(button => {
        button.addEventListener("click", () => {
            const postId = button.getAttribute("data-id");

            fetch(`/dislike?post_id=${postId}`, { method: "POST" })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    document.getElementById(`like-count-${postId}`).textContent = data.likes;
                    document.getElementById(`dislike-count-${postId}`).textContent = data.dislikes;
                } else {
                    alert(data.message || "Failed to dislike post");
                }
            })
            .catch(err => {
                console.error("Error:", err);
                alert("An error occurred while disliking the post.");
            });
        });
    });

    document.querySelectorAll(".poll-option").forEach(button => {
        button.addEventListener("click", () => {
            const postId = button.getAttribute("data-post-id");
            const index = button.getAttribute("data-index");

            fetch(`/poll/vote/${postId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ option: parseInt(index) })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    alert(data.message);
                }
            })
            .catch(err => console.error("Error:", err));
        });
    });

    document.querySelectorAll(".react-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const postId = btn.getAttribute("data-id");
            const type = btn.getAttribute("data-type");

            fetch(`/react/${postId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ type: type })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload(); // Simple for now
                }
            })
            .catch(err => console.error("Error:", err));
        });
    });

    document.querySelectorAll(".bookmark-btn").forEach(button => {
        button.addEventListener("click", () => {
            const postId = button.getAttribute("data-id");

            fetch(`/bookmark/${postId}`, { method: "POST" })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    if (data.action.includes("added")) {
                        button.textContent = "bookmark_added";
                    } else {
                        button.textContent = "bookmark";
                    }
                }
            })
            .catch(err => console.error("Error:", err));
        });
    });

    // Track views
    document.querySelectorAll(".card[data-post-id]").forEach(post => {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entries[0].isIntersecting) {
                    const postId = post.getAttribute("data-post-id");
                    fetch(`/api/post/${postId}/view`, { method: "POST" });
                    observer.unobserve(post);
                }
            });
        }, { threshold: 0.5 });
        observer.observe(post);
    });
});