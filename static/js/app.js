async function copyLink(videoId) {

    const input = document.getElementById(
        "link-" + videoId
    );

    await navigator.clipboard.writeText(
        input.value
    );

    alert("Share link copied!");
}


async function deleteVideo(videoId) {

    const confirmed = confirm(
        "Delete this video permanently?"
    );

    if (!confirmed) {
        return;
    }

    try {

        const response = await fetch(
            "/delete/" + videoId,
            {
                method: "DELETE"
            }
        );

        const data = await response.json();

        if (!response.ok) {
            alert(data.message || "Delete failed.");
            return;
        }

        alert("Video deleted.");

        window.location.reload();

    } catch (error) {

        console.error(error);

        alert(
            "Something went wrong. Please try again."
        );
    }
}