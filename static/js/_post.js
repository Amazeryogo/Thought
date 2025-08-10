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
});