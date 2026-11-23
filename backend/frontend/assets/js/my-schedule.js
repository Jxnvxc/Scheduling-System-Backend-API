const scheduleApiUrl = window.SMARTSHIFT_API_URL;
const scheduleToken = sessionStorage.getItem("access_token");
let scheduleUser = null;

try {
    scheduleUser = JSON.parse(sessionStorage.getItem("user") || "null");
} catch (error) {
    console.error("Invalid user data in session storage.", error);
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
}

if (!scheduleToken || !scheduleUser) {
    window.location.href = "index.html";
} else if (scheduleUser.role !== "employee") {
    window.location.href = "dashboard.html";
} else {
    document.getElementById("userName").textContent = scheduleUser.full_name;
    document.getElementById("topBarName").textContent = scheduleUser.full_name;
    document.getElementById("logoutButton").addEventListener("click", () => {
        sessionStorage.removeItem("access_token");
        sessionStorage.removeItem("user");
        window.location.href = "index.html";
    });
    loadMySchedule();
}

function formatScheduleDate(value) {
    return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
    });
}

function formatScheduleTime(value) {
    if (typeof value !== "string" || !/^\d{1,2}:\d{2}/.test(value)) {
        return "Time unavailable";
    }
    const [hourText, minuteText] = value.split(":");
    const hour = Number(hourText);
    const period = hour >= 12 ? "PM" : "AM";
    return `${hour % 12 || 12}:${minuteText} ${period}`;
}

function showScheduleError(message) {
    const list = document.getElementById("myScheduleList");
    const error = document.createElement("p");
    error.className = "schedule-tracking-empty is-error";
    error.textContent = message;
    list.replaceChildren(error);
}

async function loadMySchedule() {
    const list = document.getElementById("myScheduleList");
    try {
        const response = await fetch(`${scheduleApiUrl}/schedules/my`, {
            headers: { Authorization: `Bearer ${scheduleToken}` },
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Could not load your published schedule.");
        }
        if (!Array.isArray(data) || data.length === 0) {
            const empty = document.createElement("p");
            empty.className = "schedule-tracking-empty";
            empty.textContent = "Wala pang published schedule para sa iyo.";
            list.replaceChildren(empty);
            return;
        }

        const fragment = document.createDocumentFragment();
        data.forEach(schedule => {
            const card = document.createElement("article");
            card.className = "my-schedule-card";

            const heading = document.createElement("div");
            heading.className = "my-schedule-card-heading";
            const title = document.createElement("h3");
            title.textContent = formatScheduleDate(schedule.schedule_date);
            const status = document.createElement("span");
            status.className = schedule.acknowledged
                ? "schedule-response-badge is-acknowledged"
                : "schedule-response-badge is-pending";
            status.textContent = schedule.acknowledged ? "Acknowledged" : "Needs acknowledgment";
            heading.append(title, status);

            const shifts = document.createElement("ul");
            shifts.className = "my-schedule-shifts";
            schedule.assignments.forEach(assignment => {
                const item = document.createElement("li");
                const times = `${formatScheduleTime(assignment.start_time)} - ${formatScheduleTime(assignment.end_time)}`;
                item.textContent = `${assignment.station} · ${assignment.shift_name} · ${times}`;
                shifts.append(item);
            });
            card.append(heading, shifts);

            if (!schedule.acknowledged) {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "btn-primary";
                button.textContent = "I have reviewed this schedule";
                button.addEventListener("click", () => acknowledgeSchedule(schedule.schedule_date, button));
                card.append(button);
            }
            fragment.append(card);
        });
        list.replaceChildren(fragment);
    } catch (error) {
        console.error("Failed to load crew schedule.", error);
        showScheduleError(`Hindi ma-load ang schedule: ${error.message}`);
    }
}

async function acknowledgeSchedule(scheduleDate, button) {
    button.disabled = true;
    try {
        const response = await fetch(
            `${scheduleApiUrl}/schedules/${encodeURIComponent(scheduleDate)}/acknowledge`,
            {
                method: "POST",
                headers: { Authorization: `Bearer ${scheduleToken}` },
            },
        );
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Could not acknowledge this schedule.");
        }
        await loadMySchedule();
        if (typeof refreshScheduleNotification === "function") {
            refreshScheduleNotification();
        }
    } catch (error) {
        console.error("Failed to acknowledge crew schedule.", error);
        window.alert(`Hindi na-save ang acknowledgment: ${error.message}`);
        button.disabled = false;
    }
}
