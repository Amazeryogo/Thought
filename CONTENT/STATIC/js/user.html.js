document.addEventListener("DOMContentLoaded", function () {
    // Toggle follow icon
    const followIcon = document.getElementById("followToggle");
    if (followIcon) {
        followIcon.addEventListener("click", function () {
            const username = followIcon.dataset.username;

            fetch(`/follow/${username}`, { method: "POST" })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    followIcon.textContent = data.is_following ? "remove" : "add";
                    followIcon.dataset.following = data.is_following;
                    document.getElementById("followerCount").textContent = data.follower_count;
                } else {
                    alert(data.message || "Action failed");
                }
            })
            .catch(() => alert("Something went wrong."));
        });
    }

    // Hover popup for follower/following count
    const hoverElements = document.querySelectorAll(".hover-follow");
    hoverElements.forEach(elem => {
        let timer;
        elem.addEventListener("mouseenter", () => {
            const username = elem.dataset.username;
            const type = elem.dataset.type;
            timer = setTimeout(() => {
                openFollowModal(username, type);
            }, 300); // Delay to avoid accidental hover
        });
        elem.addEventListener("mouseleave", () => {
            clearTimeout(timer);
        });
    });

    // Gallery Modal Logic
    $('#galleryModal').on('show.bs.modal', function (event) {
        const button = $(event.relatedTarget);
        const imageUrl = button.data('image-url');
        const imageId = button.data('image-id');

        const modal = $(this);
        modal.find('#galleryModalImage').attr('src', imageUrl);
        modal.find('#downloadButton').attr('href', imageUrl);

        const likeCount = modal.find('#likeCount');
        const dislikeCount = modal.find('#dislikeCount');

        // Fetch initial like/dislike counts
        fetch(`/gallery/image/${imageId}/counts`)
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    likeCount.text(data.likes);
                    dislikeCount.text(data.dislikes);
                }
            });

        modal.find('#deleteImageButton').off('click').on('click', function() {
            fetch(`/gallery/image/${imageId}/delete`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert(data.message || 'Could not delete image.');
                    }
                });
        });

        modal.find('#likeButton').off('click').on('click', function() {
            fetch(`/gallery/image/${imageId}/like`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        likeCount.text(data.likes);
                        dislikeCount.text(data.dislikes);
                    }
                });
        });

        modal.find('#dislikeButton').off('click').on('click', function() {
            fetch(`/gallery/image/${imageId}/dislike`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        likeCount.text(data.likes);
                        dislikeCount.text(data.dislikes);
                    }
                });
        });
    });
});

function openFollowModal(username, type) {
    const url = type === 'followers'
        ? `/followers/${username}`
        : `/following/${username}`;

    fetch(url)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const list = data.users;
                let html = '';
                if (list.length === 0) {
                    html = `<p class="text-muted">No ${type} yet.</p>`;
                } else {
                    html = '<ul class="list-group">';
                    list.forEach(u => {
                        html += `<li class="list-group-item"><a href="/${u}">${u}</a></li>`;
                    });
                    html += '</ul>';
                }
                document.getElementById('followModalLabel').textContent = type.charAt(0).toUpperCase() + type.slice(1);
                document.getElementById('followList').innerHTML = html;
                const modal = new bootstrap.Modal(document.getElementById('followModal'));
                modal.show();
            } else {
                alert("Could not load data.");
            }
        })
        .catch(() => alert("Server error"));
}
