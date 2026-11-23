async function refreshScheduleNotification() {
    const token = sessionStorage.getItem("access_token");
    let user;
    try {
        user = JSON.parse(sessionStorage.getItem("user") || "null");
    } catch (error) {
        console.error("Invalid user data in session storage.", error);
        return;
    }
    if (!token || user?.role !== "employee") return;

    try {
        const response = await fetch(`${window.SMARTSHIFT_API_URL}/schedules/my`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || "Could not check for schedule updates.");
        }
        const schedules = await response.json();
        const pendingCount = schedules.filter(schedule => !schedule.acknowledged).length;
        document.querySelectorAll('a[href="my-schedule.html"]').forEach(link => {
            link.querySelector(".schedule-notification-badge")?.remove();
            if (pendingCount === 0) return;
            const badge = document.createElement("span");
            badge.className = "schedule-notification-badge";
            badge.textContent = String(pendingCount);
            badge.setAttribute("aria-label", `${pendingCount} schedule${pendingCount === 1 ? "" : "s"} need acknowledgment`);
            link.append(badge);
        });
    } catch (error) {
        console.error("Could not check crew schedule notifications.", error);
    }
}

refreshScheduleNotification();
