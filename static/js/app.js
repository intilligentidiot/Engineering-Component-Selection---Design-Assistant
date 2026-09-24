document.addEventListener("DOMContentLoaded", () => {
    checkHealth();
});

async function checkHealth() {
    const statusDiv = document.getElementById("api-status");
    try {
        const response = await fetch("/health");
        if (response.ok) {
            const data = await response.json();
            statusDiv.textContent = `API Status: ${data.status.toUpperCase()}`;
            statusDiv.style.color = "green";
        } else {
            throw new Error("Network response was not ok");
        }
    } catch (error) {
        statusDiv.textContent = "API Status: OFFLINE";
        statusDiv.style.color = "red";
        console.error("Error checking health:", error);
    }
}
