document.addEventListener("DOMContentLoaded", function () {
    // 1. Follow Toggle Logic
    const followIcon = document.getElementById("followToggle");
    if (followIcon) {
        followIcon.addEventListener("click", function () {
            const username = followIcon.dataset.username;

            fetch(`/follow/${username}`, { method: "POST" })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        followIcon.dataset.following = data.is_following;
                        if (data.action === 'requested') {
                            followIcon.textContent = "hour_glass";
                        } else if (data.action === 'request cancelled') {
                            followIcon.textContent = "person_add";
                        } else {
                            followIcon.textContent = data.is_following ? "person_remove" : "person_add";
                        }
                        document.getElementById("followerCount").textContent = data.follower_count;
                    } else {
                        alert(data.message || "Action failed");
                    }
                })
                .catch(() => alert("Something went wrong."));
        });
    }
    // 2. Gallery Modal Logic
    const mediaTriggers = document.querySelectorAll('.media-trigger');
    const galleryModalBody = document.getElementById('galleryModalBody');
    const galleryModalEl = document.getElementById('galleryModal');

    if (galleryModalEl && galleryModalBody) {
        const bsGalleryModal = new bootstrap.Modal(galleryModalEl);

        mediaTriggers.forEach(trigger => {
            trigger.addEventListener('click', function () {
                const type = this.getAttribute('data-type');
                const src = this.getAttribute('data-src');

                if (type === 'video') {
                    galleryModalBody.innerHTML = `
                        <video controls autoplay class="img-fluid rounded" style="max-height: 80vh;">
                            <source src="${src}" type="video/mp4">
                        </video>`;
                } else {
                    galleryModalBody.innerHTML = `
                        <img src="${src}" class="img-fluid rounded" style="max-height: 80vh;" alt="Preview">`;
                }
                bsGalleryModal.show();
            });
        });

        // Clear content when modal is closed to stop video audio
        galleryModalEl.addEventListener('hidden.bs.modal', function () {
            galleryModalBody.innerHTML = '';
        });
    }

    // 3. Hover popup for follower/following count
    const hoverElements = document.querySelectorAll(".hover-follow");
    hoverElements.forEach(elem => {
        let timer;
        elem.addEventListener("mouseenter", () => {
            const username = elem.dataset.username;
            const type = elem.dataset.type;
            timer = setTimeout(() => {
                openFollowModal(username, type);
            }, 300);
        });
        elem.addEventListener("mouseleave", () => {
            clearTimeout(timer);
        });
    });
});

// Modal function stays outside the DOMContentLoaded listener
function openFollowModal(username, type) {
    const url = type === 'followers' ? `/followers/${username}` : `/following/${username}`;

    fetch(url)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const list = data.users;
                let html = '';
                if (list.length === 0) {
                    html = `<p class="text-muted">No ${type} yet.</p>`;
                } else {
                    html = '<ul class="list-group list-group-flush">';
                    list.forEach(u => {
                        html += `<li class="list-group-item"><a href="/${u}" class="text-decoration-none">${u}</a></li>`;
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