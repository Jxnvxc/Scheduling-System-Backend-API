const API_URL = window.SMARTSHIFT_API_URL;
const token = sessionStorage.getItem("access_token");
let user;
try {
    user = JSON.parse(sessionStorage.getItem("user") || "null");
} catch {
    user = null;
}

if (!token || !user) window.location.replace("index.html");

document.getElementById("userName").textContent = user?.full_name || "";
document.getElementById("userRole").textContent = user?.role === "employee" ? "Crew" : "Manager";
document.getElementById("topBarName").textContent = user?.full_name || "";
document.getElementById("logoutButton").addEventListener("click", () => {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    window.location.replace("index.html");
});

document.querySelectorAll(user?.role === "manager" ? ".crew-only" : ".manager-only")
    .forEach(element => element.style.display = "none");
if (!["manager", "employee"].includes(user?.role)) {
    window.location.replace("dashboard.html");
}

const message = document.getElementById("requestMessage");
const authHeaders = { Authorization: "Bearer " + token };

function showMessage(text, type = "error") {
    message.textContent = text;
    message.className = `status-message is-${type}`;
}

async function requestJson(path, options = {}) {
    const response = await fetch(`${API_URL}${path}`, {
        ...options,
        headers: {
            ...authHeaders,
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...options.headers,
        },
    });
    const data = response.status === 204 ? null : await response.json();
    if (response.status === 401) {
        sessionStorage.removeItem("access_token");
        sessionStorage.removeItem("user");
        window.location.replace("index.html?session=expired");
        throw new Error("Session expired. Please sign in again.");
    }
    if (!response.ok) {
        const detail = typeof data?.detail === "string" ? data.detail : "Request failed.";
        throw new Error(detail);
    }
    return data;
}

function addText(parent, tag, text, className) {
    const element = document.createElement(tag);
    element.textContent = text;
    if (className) element.className = className;
    parent.append(element);
    return element;
}

function shiftLabel(shift) {
    if (!shift) return "Shift unavailable";
    const time = shift.start_time && shift.end_time
        ? ` · ${shift.start_time}–${shift.end_time}`
        : "";
    return `${shift.date} · ${shift.shift} · ${shift.station}${time}`;
}

function renderRequestCard(request, isManager) {
    const card = document.createElement("article");
    card.className = "request-card";
    const title = request.request_type === "leave" ? "Leave request" : "Shift swap";
    addText(card, "h3", isManager ? `${title} · ${request.requester_name}` : title);
    addText(card, "span", request.status.replaceAll("_", " "), "request-status");

    if (request.request_type === "leave") {
        addText(card, "p", `${request.start_date} to ${request.end_date}`);
        if (request.conflicting_assignments > 0) {
            addText(
                card,
                "p",
                `Warning: ${request.conflicting_assignments} published shift(s) overlap these dates. Approval will not remove those shifts.`,
                "request-warning",
            );
        }
    } else {
        addText(card, "p", `Requester: ${request.requester_name}`);
        addText(card, "p", `Requested shift: ${shiftLabel(request.requester_shift)}`);
        addText(card, "p", `${request.target_name ? `Swap with ${request.target_name}: ` : "Other shift: "}${shiftLabel(request.target_shift)}`);
    }
    if (request.reason) addText(card, "p", `Note: ${request.reason}`);

    const actions = document.createElement("div");
    actions.className = "request-actions";
    if (isManager && request.status === "pending_manager") {
        actions.append(
            createActionButton("Approve", () => decideRequest(request.id, "approve"), "btn-primary"),
            createActionButton("Reject", () => decideRequest(request.id, "reject"), "btn-secondary"),
        );
    } else if (
        !isManager
        && request.request_type === "swap"
        && request.target_user_id === user.id
        && request.status === "pending_recipient"
    ) {
        actions.append(
            createActionButton("Accept", () => respondToSwap(request.id, true), "btn-primary"),
            createActionButton("Decline", () => respondToSwap(request.id, false), "btn-secondary"),
        );
    }
    if (actions.childElementCount) card.append(actions);
    return card;
}

function createActionButton(label, action, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    button.addEventListener("click", action);
    return button;
}

async function loadCrewRequests() {
    const container = document.getElementById("crewRequestsList");
    const requests = await requestJson("/requests/my");
    container.replaceChildren();
    if (!requests.length) {
        addText(container, "p", "Wala ka pang requests.");
        return;
    }
    requests.forEach(request => container.append(renderRequestCard(request, false)));
}

async function loadManagerRequests() {
    const container = document.getElementById("managerRequestsList");
    const requests = await requestJson("/requests/manager");
    container.replaceChildren();
    if (!requests.length) {
        addText(container, "p", "Walang pending approvals.");
        return;
    }
    requests.forEach(request => container.append(renderRequestCard(request, true)));
}

async function loadSwapOptions() {
    const data = await requestJson("/requests/swap-options");
    const ownSelect = document.querySelector("#swapRequestForm [name='requester_assignment_id']");
    const targetSelect = document.querySelector("#swapRequestForm [name='target_assignment_id']");
    for (const [select, shifts, placeholder] of [
        [ownSelect, data.my_shifts, "Select your published shift"],
        [targetSelect, data.crew_shifts, "Select another crew member's shift"],
    ]) {
        select.replaceChildren(new Option(placeholder, ""));
        shifts.forEach(shift => {
            select.add(new Option(`${shiftLabel(shift)} · ${shift.crew_name}`, shift.id));
        });
        select.disabled = shifts.length === 0;
    }
    document.querySelector("#swapRequestForm button[type='submit']").disabled =
        data.my_shifts.length === 0 || data.crew_shifts.length === 0;
}

async function respondToSwap(requestId, accept) {
    try {
        await requestJson(`/requests/${requestId}/swap-response`, {
            method: "POST",
            body: JSON.stringify({ accept }),
        });
        showMessage(accept ? "Tinanggap ang swap request. Ipapasa ito sa manager." : "Tinanggihan ang swap request.", "success");
        await loadCrewRequests();
    } catch (error) {
        showMessage(error.message);
    }
}

async function decideRequest(requestId, decision) {
    try {
        await requestJson(`/requests/${requestId}/decision`, {
            method: "POST",
            body: JSON.stringify({ decision }),
        });
        showMessage(`Request ${decision === "approve" ? "approved" : "rejected"}.`, "success");
        await loadManagerRequests();
    } catch (error) {
        showMessage(error.message);
    }
}

if (user?.role === "employee") {
    document.getElementById("leaveRequestForm").addEventListener("submit", async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = new FormData(form);
        try {
            await requestJson("/requests/leave", {
                method: "POST",
                body: JSON.stringify({
                    start_date: values.get("start_date"),
                    end_date: values.get("end_date"),
                    reason: values.get("reason") || null,
                }),
            });
            form.reset();
            showMessage("Leave request submitted for manager approval.", "success");
            await loadCrewRequests();
        } catch (error) {
            showMessage(error.message);
        }
    });

    document.getElementById("swapRequestForm").addEventListener("submit", async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = new FormData(form);
        try {
            await requestJson("/requests/swaps", {
                method: "POST",
                body: JSON.stringify({
                    requester_assignment_id: Number(values.get("requester_assignment_id")),
                    target_assignment_id: Number(values.get("target_assignment_id")),
                    reason: values.get("reason") || null,
                }),
            });
            form.reset();
            showMessage("Swap request sent to the other crew member.", "success");
            await Promise.all([loadCrewRequests(), loadSwapOptions()]);
        } catch (error) {
            showMessage(error.message);
        }
    });
}

if (user?.role === "manager") {
    loadManagerRequests().catch(error => showMessage(error.message));
} else if (user?.role === "employee") {
    Promise.all([loadCrewRequests(), loadSwapOptions()])
        .catch(error => showMessage(error.message));
}
