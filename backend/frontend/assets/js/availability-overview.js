const API_URL = window.SMARTSHIFT_API_URL;
const token = sessionStorage.getItem("access_token");
const user = sessionStorage.getItem("user")
    ? JSON.parse(sessionStorage.getItem("user"))
    : null;

const availMessage = document.getElementById("availMessage");
const availCount = document.getElementById("availCount");
const weekStartInput = document.getElementById("week_start");
const filterRole = document.getElementById("filter_role");
const filterEmployment = document.getElementById("filter_employment");
const filterDay = document.getElementById("filter_day");
const searchCrew = document.getElementById("search_crew");
const gridBody = document.getElementById("availGridBody");
const gridFoot = document.getElementById("availGridFoot");
const slotBody = document.getElementById("slotBody");
const slotSummary = document.getElementById("slotSummary");
const slotDaySelect = document.getElementById("slot_day");
const viewButtons = document.querySelectorAll(".view-btn");
const viewGrid = document.getElementById("viewGrid");
const viewSlot = document.getElementById("viewSlot");

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const SHIFTS = [
  { name: "Opening", start: "08:00", end: "16:00" },
  { name: "Mid", start: "12:00", end: "20:00" },
  { name: "Closing", start: "14:00", end: "22:00" },
];

let overviewData = null;

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[character]);
}

function showMessage(message, type = "") {
    availMessage.textContent = message;
    availMessage.className = `crew-message${message ? " is-visible" : ""}${type ? ` is-${type}` : ""}`;
}

function formatTime(hhmm) {
    if (!hhmm) return "";
    const [h, m] = String(hhmm).split(":").map(Number);
    if (h == null || m == null) return hhmm;
    const period = h >= 12 ? "PM" : "AM";
    const hour12 = h % 12 || 12;
    return `${hour12}:${String(m).padStart(2, "0")} ${period}`;
}

function formatWindows(windows) {
    if (!windows || windows.length === 0) return null;
    return windows.map(w => `${formatTime(w.start)} - ${formatTime(w.end)}`).join("<br>");
}

async function requestJson(path, options = {}) {
    const response = await fetch(`${API_URL}${path}`, {
        ...options,
        headers: {
            Authorization: `Bearer ${token}`,
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...options.headers
        }
    });

    if (response.status === 204) {
        if (!response.ok) throw new Error(`Request failed (${response.status}).`);
        return null;
    }

    let data;
    try {
        data = await response.json();
    } catch (error) {
        throw new Error(`The server returned an invalid response (${response.status}).`, { cause: error });
    }

    if (!response.ok) {
        const detail = data && data.detail;
        const error = new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
        error.responseData = data;
        throw error;
    }
    return data;
}

function defaultWeekStart() {
    const today = new Date();
    const day = today.getDay(); // 0=Sun, 1=Mon, ...
    const mondayOffset = day === 0 ? -6 : 1 - day;
    const monday = new Date(today);
    monday.setDate(today.getDate() + mondayOffset);
    return monday.toISOString().split("T")[0];
}

function matchesFilters(member) {
    const role = filterRole.value;
    const employment = filterEmployment.value;
    const day = filterDay.value;
    const q = String(searchCrew.value || "").trim().toLowerCase();

    if (role && !String(member.crew_type || "").includes(role)) return false;
    if (employment && member.employment_type !== employment) return false;
    if (q && !String(member.full_name || "").toLowerCase().includes(q)
        && !String(member.employee_number || "").toLowerCase().includes(q)) return false;

    if (day) {
        const windows = (member.days || {})[day] || [];
        if (!windows || windows.length === 0) return false;
    }
    return true;
}

function renderGrid(data) {
    gridBody.innerHTML = "";
    const filtered = data.crew.filter(matchesFilters);

    availCount.textContent = `${filtered.length} ${filtered.length === 1 ? "crew member" : "crew members"}`;
    if (filtered.length === 0) {
        gridBody.innerHTML = `<tr><td colspan="11" class="empty-grid-cell">Wala pang crew na tutugma sa filter na pinili.</td></tr>`;
        gridFoot.innerHTML = "";
        return;
    }

    const availablePerDay = data.available_per_day || {};

    filtered.forEach(member => {
        const row = document.createElement("tr");
        const hasBadge = !member.has_availability
            ? `<span class="avail-badge none">Walang availability</span>`
            : "";
        row.innerHTML = `
            <td class="col-sticky crew-name-cell">
                <div class="crew-name">${escapeHtml(member.full_name)}</div>
                <div class="crew-meta">
                    <span class="crew-id">${escapeHtml(member.employee_number || "—")}</span>
                    ${hasBadge}
                </div>
            </td>
            <td class="crew-id-cell">${escapeHtml(member.employee_number || "—")}</td>
            <td>${escapeHtml(member.employment_type || "—")}</td>
            <td>${escapeHtml(member.crew_type || "—")}</td>
        `;

        DAYS.forEach(dayName => {
            const cell = document.createElement("td");
            cell.className = "col-day";
            const windows = (member.days || {})[dayName] || [];
            if (windows && windows.length > 0) {
                cell.innerHTML = formatWindows(windows);
                cell.classList.add("has-avail");
            } else {
                cell.textContent = "Hindi available";
                cell.classList.add("no-avail");
            }
            row.append(cell);
        });

        const actionsCell = document.createElement("td");
        actionsCell.className = "col-actions";
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn-edit";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", (event) => {
            event.stopPropagation();
            openEditModal(member);
        });
        actionsCell.append(editBtn);
        row.append(actionsCell);
        gridBody.append(row);
    });

    // Summary footer row: total available per day
    const foot = document.createElement("tr");
    foot.innerHTML = `
        <td class="col-sticky summary-label" colspan="4">Total available</td>
    `;
    DAYS.forEach(dayName => {
        const count = availablePerDay[dayName] || 0;
        const td = document.createElement("td");
        td.className = "col-day summary-count";
        td.textContent = count;
        foot.append(td);
    });
    gridFoot.innerHTML = "";
    gridFoot.append(foot);
}

function renderSlotView(data) {
    slotBody.innerHTML = "";
    slotSummary.innerHTML = "";

    // Populate day select
    slotDaySelect.innerHTML = "";
    data.days.forEach(dayName => {
        const opt = document.createElement("option");
        opt.value = dayName;
        opt.textContent = dayName;
        slotDaySelect.append(opt);
    });

    function draw(dayName) {
        slotBody.innerHTML = "";
        const filtered = data.crew.filter(matchesFilters);
        const countAvailable = filtered.filter(m => {
            const w = (m.days || {})[dayName] || [];
            return w && w.length > 0;
        }).length;

        const summary = document.createElement("div");
        summary.className = "slot-count-summary";
        summary.textContent = `${countAvailable} of ${filtered.length} crew available on ${dayName}`;
        slotSummary.innerHTML = "";
        slotSummary.append(summary);

        SHIFTS.forEach(shift => {
            const available = [];
            filtered.forEach(member => {
                const windows = (member.days || {})[dayName] || [];
                const covers = windows.some(w => w.start <= shift.start && w.end >= shift.end);
                if (covers) available.push(member);
            });

            const card = document.createElement("div");
            card.className = "slot-card";
            const title = document.createElement("div");
            title.className = "slot-title";
            title.textContent = `${shift.name} (${shift.start} - ${shift.end})`;
            const count = document.createElement("div");
            count.className = "slot-count";
            count.textContent = `${available.length} crew`;
            card.append(title, count);

            const list = document.createElement("ul");
            list.className = "slot-crew-list";
            if (available.length === 0) {
                const li = document.createElement("li");
                li.textContent = "Walang available crew";
                li.className = "slot-none";
                list.append(li);
            } else {
                available.forEach(member => {
                    const li = document.createElement("li");
                    const idTxt = member.employee_number ? ` (${escapeHtml(member.employee_number)})` : "";
                    li.textContent = `${escapeHtml(member.full_name)}${idTxt}`;
                    list.append(li);
                });
            }
            card.append(list);
            slotBody.append(card);
        });
    }

    draw(slotDaySelect.value || data.days[0]);
    slotDaySelect.addEventListener("change", () => draw(slotDaySelect.value));
}

function renderViews(data) {
    overviewData = data;
    renderGrid(data);
    renderSlotView(data);
}

async function loadOverview() {
    const weekStart = weekStartInput.value;
    if (!weekStart) return;
    gridBody.innerHTML = `<tr><td colspan="11" class="empty-grid-cell">Loading crew availability...</td></tr>`;
    slotBody.innerHTML = `<div class="empty-state">Loading...</div>`;
    showMessage("Loading availability overview...");
    try {
        const data = await requestJson(`/availability/overview?week_start=${encodeURIComponent(weekStart)}`);
        renderViews(data);
        showMessage("");
    } catch (error) {
        gridBody.innerHTML = `<tr><td colspan="11" class="empty-grid-cell">Hindi ma-load ang availability: ${escapeHtml(error.message)}</td></tr>`;
        showMessage(`Hindi ma-load ang availability: ${error.message}`, "error");
    }
}

function applyFilters() {
    if (!overviewData) return;
    renderGrid(overviewData);
    renderSlotView(overviewData);
}

function setView(view) {
    viewButtons.forEach(btn => {
        btn.classList.toggle("active", btn.dataset.view === view);
    });
    if (view === "grid") {
        viewGrid.style.display = "";
        viewSlot.style.display = "none";
    } else {
        viewGrid.style.display = "none";
        viewSlot.style.display = "";
    }
}

function logout() {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    window.location.href = "index.html";
}

// ===== EDIT AVAILABILITY MODAL =====
const availEditModal = document.getElementById("availEditModal");
const availEditModalClose = document.getElementById("availEditModalClose");
const availEditCancel = document.getElementById("availEditCancel");
const availEditSave = document.getElementById("availEditSave");
const availEditSaveMessage = document.getElementById("availEditSaveMessage");
const availEditDaysContainer = document.getElementById("availEditDaysContainer");
const availEditModalTitle = document.getElementById("availEditModalTitle");
const availEditModalSub = document.getElementById("availEditModalSub");

const availConfirmModal = document.getElementById("availConfirmModal");
const availConfirmClose = document.getElementById("availConfirmClose");
const availConfirmCancel = document.getElementById("availConfirmCancel");
const availConfirmSave = document.getElementById("availConfirmSave");
const availConfirmMessage = document.getElementById("availConfirmMessage");
const availConfirmList = document.getElementById("availConfirmList");

let editingMemberId = null;

function todayISO() {
    const d = new Date();
    return d.toISOString().split("T")[0];
}

function truncateTime(t) {
    if (!t) return "";
    return String(t).substring(0, 5);
}

function openEditModal(member) {
    editingMemberId = member.id;
    pendingSaveWindows = null;
    availEditModalTitle.textContent = `Edit availability - ${escapeHtml(member.full_name)}`;
    availEditModalSub.textContent = `Employee ID: ${escapeHtml(member.employee_number || "—")}`;
    availEditSaveMessage.style.display = "none";
    availEditSaveMessage.textContent = "";
    availEditDaysContainer.innerHTML = "";

    requestJson(`/availability/crew/${member.id}`)
        .then(data => {
            renderEditWindows(data.windows || []);
            availEditModal.style.display = "flex";
            availEditModal.setAttribute("aria-hidden", "false");
        })
        .catch(error => {
            showMessage(`Hindi ma-load ang availability: ${error.message}`, "error");
        });
}

function closeEditModal() {
    availEditModal.style.display = "none";
    availEditModal.setAttribute("aria-hidden", "true");
    editingMemberId = null;
    pendingSaveWindows = null;
    availEditDaysContainer.innerHTML = "";
}

function renderEditWindows(windows) {
    availEditDaysContainer.innerHTML = "";
    DAYS.forEach(dayName => {
        const dayWindows = windows.filter(w => w.day_of_week === dayName);
        const section = document.createElement("div");
        section.className = "avail-edit-day";
        section.style.marginBottom = "16px";

        const header = document.createElement("h3");
        header.textContent = dayName;
        header.style.cssText = "margin:0 0 8px;font-size:13px;color:var(--text-main);";
        section.append(header);

        const list = document.createElement("div");
        list.className = "avail-edit-day-windows";
        list.style.cssText = "display:flex;flex-direction:column;gap:8px;";

        dayWindows.forEach(w => {
            addWindowRow(list, dayName, w);
        });

        section.append(list);

        const addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "btn-secondary";
        addBtn.textContent = "Add window";
        addBtn.style.cssText = "font-size:11px;padding:6px 10px;margin-top:6px;align-self:flex-start;";
        addBtn.addEventListener("click", () => {
            addWindowRow(list, dayName, {
                day_of_week: dayName,
                start_time: "08:00",
                end_time: "17:00",
                valid_from: todayISO(),
                valid_to: todayISO(),
            });
        });
        section.append(addBtn);

        availEditDaysContainer.append(section);
    });
}

function addWindowRow(list, dayName, w) {
    const row = document.createElement("div");
    row.className = "avail-edit-window";
    row.style.cssText = "display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) auto;gap:8px;align-items:end;";
    row.innerHTML = `
        <input type="time" class="edit-start" value="${truncateTime(w.start_time)}" />
        <input type="time" class="edit-end" value="${truncateTime(w.end_time)}" />
        <input type="date" class="edit-valid-from" value="${w.valid_from || todayISO()}" />
        <input type="date" class="edit-valid-to" value="${w.valid_to || todayISO()}" />
        <button type="button" class="btn-delete edit-remove" style="padding:6px 10px;font-size:11px;">Remove</button>
    `;
    row.querySelector(".edit-remove").addEventListener("click", () => row.remove());
    list.append(row);
}

function collectEditWindows() {
    const windows = [];
    const sections = availEditDaysContainer.querySelectorAll(".avail-edit-day");
    sections.forEach(section => {
        const dayName = section.querySelector("h3").textContent;
        const rows = section.querySelectorAll(".avail-edit-window");
        rows.forEach(row => {
            const start = row.querySelector(".edit-start").value;
            const end = row.querySelector(".edit-end").value;
            const vf = row.querySelector(".edit-valid-from").value;
            const vt = row.querySelector(".edit-valid-to").value;
            if (start && end && vf && vt) {
                windows.push({ day_of_week: dayName, start_time: start, end_time: end, valid_from: vf, valid_to: vt });
            }
        });
    });
    return windows;
}

function showSaveError(message) {
    availEditSaveMessage.textContent = message;
    availEditSaveMessage.style.display = "block";
}

function saveEditAvailability() {
    if (!editingMemberId) return;
    const windows = collectEditWindows();
    if (windows.length === 0) {
        showSaveError("Magdagdag ng o kusa bago i-save.");
        return;
    }
    availEditSave.disabled = true;
    availEditSave.textContent = "Saving...";
    requestJson(`/availability/crew/${editingMemberId}`, {
        method: "PUT",
        body: JSON.stringify({ windows, confirm: false }),
    })
        .then(data => {
            availEditSave.disabled = false;
            availEditSave.textContent = "Save changes";
            closeEditModal();
            loadOverview();
        })
        .catch(error => {
            availEditSave.disabled = false;
            availEditSave.textContent = "Save changes";
            showSaveError(error.message || "Hindi ma-save ang availability.");
        });
}

if (!token || !user) {
    window.location.href = "index.html";
} else if (user.role !== "manager") {
    window.location.href = user.role === "head" ? "head-dashboard.html" : "dashboard.html";
} else {
    document.getElementById("userName").textContent = user.full_name;
    document.getElementById("topBarName").textContent = user.full_name;
    document.getElementById("userRole").textContent = user.role === "manager" ? "Manager" : "Crew";

    weekStartInput.value = defaultWeekStart();

    [weekStartInput, filterRole, filterEmployment, filterDay, searchCrew].forEach(el => {
        el.addEventListener("change", () => {
            if (el === weekStartInput) loadOverview();
            else applyFilters();
        });
    });
    searchCrew.addEventListener("input", applyFilters);

    viewButtons.forEach(btn => {
        btn.addEventListener("click", () => setView(btn.dataset.view));
    });

    document.getElementById("logoutButton").addEventListener("click", logout);

    availEditModalClose.addEventListener("click", closeEditModal);
    availEditCancel.addEventListener("click", closeEditModal);
    availEditSave.addEventListener("click", saveEditAvailability);

    // Close modal when clicking outside
    availEditModal.addEventListener("click", event => {
        if (event.target === availEditModal) closeEditModal();
    });

    loadOverview();
}
