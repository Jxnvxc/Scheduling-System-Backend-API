const API_URL = window.SMARTSHIFT_API_URL;
const token = sessionStorage.getItem("access_token");
const userString = sessionStorage.getItem("user");
const form = document.getElementById("requirementsForm");
const tableBody = document.getElementById("requirementsTableBody");
const saveButton = document.getElementById("saveRequirementsButton");
const message = document.getElementById("requirementsMessage");

let stationPriorities = new Map(); // station_id -> priority (1=critical, 2=important, 3=can be empty)

if (!token || !userString) window.location.replace("index.html");

let user = null;
try {
    user = JSON.parse(userString);
} catch {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    window.location.replace("index.html");
}

if (user && user.role !== "manager") {
    window.location.replace("dashboard.html");
}

if (user) {
    document.getElementById("userName").textContent = user.full_name || "";
    document.getElementById("topBarName").textContent = user.full_name || "";
    document.getElementById("userRole").textContent =
        user.role === "manager" ? "Manager" : "Crew";
}

document.getElementById("logoutButton").addEventListener("click", () => {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    window.location.replace("index.html");
});

function showMessage(text, type = "error") {
    message.textContent = text;
    message.className = `status-message is-${type}`;
}

function formatApiError(detail, fallback) {
    if (detail == null) return fallback;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
        const messages = detail
            .filter(item => item && typeof item === "object")
            .map(item => {
                const location = Array.isArray(item.loc)
                    ? item.loc.filter(part => part !== "body").join(" > ")
                    : "";
                return [location, item.msg].filter(Boolean).join(": ");
            })
            .filter(Boolean);
        if (messages.length) return messages.join("; ");
    }
    if (typeof detail === "object") {
        if (typeof detail.message === "string") return detail.message;
        if (typeof detail.detail === "string") return detail.detail;
    }
    return fallback;
}

async function requestJson(path, options = {}) {
    const response = await fetch(`${API_URL}${path}`, {
        ...options,
        headers: {
            Authorization: `Bearer ${token}`,
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...options.headers,
        },
    });

    if (response.status === 401) {
        sessionStorage.removeItem("access_token");
        sessionStorage.removeItem("user");
        window.location.replace("index.html?session=expired");
        throw new Error("Session expired. Please sign in again.");
    }

    let data;
    try {
        data = await response.json();
    } catch {
        if (!response.ok) {
            throw new Error(`Unable to save staffing requirements. (HTTP ${response.status})`);
        }
        return null;
    }

    if (!response.ok) {
        throw new Error(formatApiError(data && data.detail, "Unable to save staffing requirements."));
    }
    return data;
}

// Normalize HH:MM (from <input type="time">) to HH:MM:SS for Pydantic time fields.
function normalizeTime(value) {
    if (!value) return value;
    const parts = String(value).split(":");
    if (parts.length === 2) return `${parts[0]}:${parts[1]}:00`;
    return value;
}

function renderRequirements(requirements, stationPriorities = new Map()) {
    tableBody.replaceChildren();
    const reqs = requirements || [];
    if (reqs.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 6;
        cell.textContent = "Add a station before setting staffing requirements.";
        row.append(cell);
        tableBody.append(row);
        saveButton.disabled = true;
        return;
    }

    const kitchenOrder = ["Prepping", "Initiator 1", "Initiator 2", "Batch Grill", "Batch Fry", "Expert", "Assembler 1"];
    const bottomOrder = ["Maintenance", "Inventory Assistance"];
    const kitchenRank = new Map();
    kitchenOrder.forEach((name, index) => kitchenRank.set(name.toLowerCase(), index));
    const bottomRank = new Map();
    bottomOrder.forEach((name, index) => bottomRank.set(name.toLowerCase(), index));

    const shiftsByStation = new Map();
    reqs.forEach(requirement => {
        const shifts = shiftsByStation.get(requirement.station_id) || [];
        shifts.push(requirement);
        shiftsByStation.set(requirement.station_id, shifts);
    });

    const sortedStations = Array.from(shiftsByStation.entries())
        .sort(([, shiftsA], [, shiftsB]) => {
            const nameA = shiftsA[0].station_name.toLowerCase();
            const nameB = shiftsB[0].station_name.toLowerCase();
            const rankA = kitchenRank.get(nameA);
            const rankB = kitchenRank.get(nameB);
            const bottomRankA = bottomRank.get(nameA);
            const bottomRankB = bottomRank.get(nameB);
            const aIsKitchen = rankA !== undefined;
            const bIsKitchen = rankB !== undefined;
            const aIsBottom = bottomRankA !== undefined;
            const bIsBottom = bottomRankB !== undefined;
            if (aIsKitchen && bIsKitchen) return rankA - rankB;
            if (aIsKitchen && !bIsKitchen) return -1;
            if (!aIsKitchen && bIsKitchen) return 1;
            if (aIsBottom && bIsBottom) return bottomRankA - bottomRankB;
            if (aIsBottom && !bIsBottom) return 1;
            if (!aIsBottom && bIsBottom) return -1;
            return shiftsA[0].station_name.localeCompare(shiftsB[0].station_name);
        });

    const fragment = document.createDocumentFragment();

    function addCategoryRow(label, categoryKey, expanded) {
        const row = document.createElement("tr");
        row.className = "staffing-category-row";
        row.dataset.category = categoryKey;
        const cell = document.createElement("td");
        cell.colSpan = 6;
        cell.className = "category-header-cell";
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "category-toggle";
        btn.textContent = label;
        btn.dataset.category = categoryKey;
        btn.setAttribute("aria-expanded", String(expanded));
        if (!expanded) btn.classList.add("is-collapsed");
        cell.append(btn);
        row.append(cell);
        fragment.append(row);
        return row;
    }

    function shiftSummary(shift, isMid = false) {
        if (!shift || shift.enabled === false) {
            return isMid ? "Mid: off" : "\u2014";
        }
        const start = formatCompactTime(shift.start_time);
        const end = formatCompactTime(shift.end_time);
        return `${start}\u2013${end} \u00b7 ${shift.required_count ?? 1} crew`;
    }

    function formatCompactTime(timeStr) {
        if (!timeStr) return "\u2013\u2013\u2013\u2013";
        const [h, m] = String(timeStr).split(":");
        const hour = parseInt(h, 10);
        const ampm = hour >= 12 ? "PM" : "AM";
        const displayHour = hour % 12 || 12;
        return `${displayHour}:${m} ${ampm}`;
    }

    let lastCategory = null;
    sortedStations.forEach(([stationId, shifts]) => {
        const stationName = shifts[0].station_name.toLowerCase();
        const isKitchen = kitchenRank.get(stationName) !== undefined;
        const isBottom = bottomRank.get(stationName) !== undefined;
        const categoryKey = isKitchen ? "kitchen" : "service";

        if (lastCategory === null) {
            addCategoryRow(isKitchen ? "Kitchen Station" : "Service Station", categoryKey, true);
        } else if (categoryKey !== lastCategory) {
            addCategoryRow("Service Station", "service", false);
        }
        lastCategory = categoryKey;

        const shiftByType = new Map();
        shifts.forEach(s => shiftByType.set(s.shift_type, s));
        const opening = shiftByType.get("Opening") || {};
        const mid = shiftByType.get("Mid") || {};
        const closing = shiftByType.get("Closing") || {};

        const stationRow = document.createElement("tr");
        stationRow.className = "staffing-station-row compact";
        stationRow.dataset.category = categoryKey;
        stationRow.dataset.stationId = String(stationId);
        stationRow.dataset.stationName = shifts[0].station_name.toLowerCase();
        if (isBottom) stationRow.classList.add("station-bottom");

        const cell = document.createElement("td");
        cell.colSpan = 6;

        const compact = document.createElement("div");
        compact.className = "station-compact";

        const nameSpan = document.createElement("span");
        nameSpan.className = "station-compact-name";
        nameSpan.textContent = shifts[0].station_name;

        const priority = stationPriorities.get(stationId) ?? 2;
        const priorityBadge = document.createElement("span");
        priorityBadge.className = `priority-badge p${priority}`;
        priorityBadge.textContent = `P${priority}`;
        priorityBadge.title = `Priority: ${priority === 1 ? "Critical" : priority === 2 ? "Important" : "Can be empty"}`;

        const openingSpan = document.createElement("span");
        openingSpan.className = "shift-summary opening";
        openingSpan.textContent = shiftSummary(opening);

        const midSpan = document.createElement("span");
        midSpan.className = "shift-summary mid";
        midSpan.textContent = shiftSummary(mid, true);

        const closingSpan = document.createElement("span");
        closingSpan.className = "shift-summary closing";
        closingSpan.textContent = shiftSummary(closing);

        const actions = document.createElement("div");
        actions.className = "station-compact-actions";
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn-secondary btn-sm btn-edit-station";
        editBtn.textContent = "Edit";
        editBtn.dataset.stationId = String(stationId);
        actions.append(editBtn);

        compact.append(nameSpan, priorityBadge, openingSpan, midSpan, closingSpan, actions);
        cell.append(compact);

        const editor = document.createElement("div");
        editor.className = "station-inline-editor";
        editor.hidden = true;
        editor.dataset.stationId = String(stationId);

        const editorTable = document.createElement("table");
        editorTable.className = "station-shift-table";
        const thead = document.createElement("thead");
        const theadRow = document.createElement("tr");
        ["Shift", "Starts", "Ends", "Required crew", "Min crew", "Enabled"].forEach(label => {
            const th = document.createElement("th");
            th.scope = "col";
            th.textContent = label;
            theadRow.append(th);
        });
        thead.append(theadRow);
        editorTable.append(thead);

        const tbody = document.createElement("tbody");
        ["Opening", "Mid", "Closing"].forEach(shiftType => {
            const shift = shiftByType.get(shiftType);
            tbody.append(createEditorShiftRow(shift, shiftType, shifts[0].station_name, shift && shift.minimum_crew));
        });
        editorTable.append(tbody);

        const priorityControl = document.createElement("div");
        priorityControl.className = "station-priority-control";
        const priorityLabel = document.createElement("label");
        priorityLabel.textContent = "Station priority";
        priorityLabel.style.cssText = "font-size:12px;font-weight:600;margin-right:8px;color:var(--text-main);";
        const prioritySelect = document.createElement("select");
        prioritySelect.className = "station-priority-input";
        prioritySelect.style.cssText = "padding:6px 10px;font-size:13px;border:1px solid #cbd9d6;border-radius:6px;background:#fff;color:var(--text-main);min-width:110px;";
        [1, 2, 3].forEach(p => {
            const opt = document.createElement("option");
            opt.value = p;
            opt.textContent = p === 1 ? "1 – Critical" : p === 2 ? "2 – Important" : "3 – Can be empty";
            opt.selected = p === (stationPriorities.get(stationId) ?? 2);
            prioritySelect.append(opt);
        });
        priorityControl.append(priorityLabel, prioritySelect);

        const applyBtn = document.createElement("button");
        applyBtn.type = "button";
        applyBtn.className = "btn-secondary btn-apply-shift-times";
        applyBtn.textContent = "Apply these shift hours to all stations";
        applyBtn.addEventListener("click", () => applyShiftTimesToAll(stationId));

        editor.append(priorityControl, editorTable, applyBtn);
        cell.append(editor);
        stationRow.append(cell);

        fragment.append(stationRow);
    });

    tableBody.append(fragment);

    document.querySelectorAll(".category-toggle").forEach(btn => {
        btn.addEventListener("click", () => {
            const key = btn.dataset.category;
            const expanded = btn.getAttribute("aria-expanded") === "true";
            btn.setAttribute("aria-expanded", String(!expanded));
            btn.classList.toggle("is-collapsed", !expanded);
            document.querySelectorAll(`.staffing-station-row[data-category="${key}"]`).forEach(row => {
                row.hidden = !expanded;
            });
        });
    });

    document.querySelectorAll(".btn-edit-station").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const stationId = btn.dataset.stationId;
            document.querySelectorAll(".station-inline-editor").forEach(ed => {
                if (ed.dataset.stationId !== stationId) ed.hidden = true;
            });
            const editor = document.querySelector(`.station-inline-editor[data-station-id="${stationId}"]`);
            if (editor) editor.hidden = !editor.hidden;
        });
    });

    saveButton.disabled = false;
}

function createEditorShiftRow(shift, shiftType, stationName, minimumCrew) {
    const defaults = getDefaultShiftTimes(shiftType);
    const startValue = (shift && shift.start_time ? shift.start_time.slice(0, 5) : defaults.start);
    const endValue = (shift && shift.end_time ? shift.end_time.slice(0, 5) : defaults.end);
    const enabled = shift ? shift.enabled !== false : true;
    const requiredCount = shift ? String(shift.required_count ?? 1) : "1";
    const minCrewValue = shift && shift.minimum_crew != null ? String(shift.minimum_crew) : (minimumCrew != null ? String(minimumCrew) : requiredCount);

    const row = document.createElement("tr");
    row.dataset.stationId = String(shift && shift.station_id ? shift.station_id : "");
    row.dataset.shiftType = shiftType;

    const nameCell = document.createElement("td");
    nameCell.textContent = shiftType;

    const startCell = document.createElement("td");
    const startInput = document.createElement("input");
    startInput.className = "shift-config-input";
    startInput.type = "time";
    startInput.required = true;
    startInput.value = startValue;
    startInput.setAttribute("aria-label", `${stationName} ${shiftType} start time`);
    startCell.append(startInput);

    const endCell = document.createElement("td");
    const endInput = document.createElement("input");
    endInput.className = "shift-config-input";
    endInput.type = "time";
    endInput.required = true;
    endInput.value = endValue;
    endInput.setAttribute("aria-label", `${stationName} ${shiftType} end time`);
    endCell.append(endInput);

    const countCell = document.createElement("td");
    const countInput = document.createElement("input");
    countInput.className = "requirement-count-input";
    countInput.type = "number";
    countInput.min = "0";
    countInput.max = "100";
    countInput.step = "1";
    countInput.required = true;
    countInput.value = requiredCount;
    countInput.setAttribute("aria-label", `${stationName} ${shiftType} required crew`);
    countCell.append(countInput);

    const minCell = document.createElement("td");
    const minInput = document.createElement("input");
    minInput.className = "requirement-count-input min-crew-input";
    minInput.type = "number";
    minInput.min = "0";
    minInput.max = "100";
    minInput.step = "1";
    minInput.required = true;
    minInput.value = minCrewValue;
    minInput.setAttribute("aria-label", `${stationName} ${shiftType} minimum crew`);
    minCell.append(minInput);

    const enabledCell = document.createElement("td");
    const enabledInput = document.createElement("input");
    enabledInput.className = "shift-enabled-input";
    enabledInput.type = "checkbox";
    enabledInput.checked = enabled;
    enabledInput.setAttribute("aria-label", `${stationName} ${shiftType} shift enabled`);

    const toggleShiftInputs = () => {
        const isEnabled = enabledInput.checked;
        startInput.disabled = !isEnabled;
        endInput.disabled = !isEnabled;
        countInput.disabled = !isEnabled;
        minInput.disabled = !isEnabled;
        row.classList.toggle("staffing-shift-disabled", !isEnabled);
    };
    enabledInput.addEventListener("change", toggleShiftInputs);
    toggleShiftInputs();

    enabledCell.append(enabledInput);
    row.append(nameCell, startCell, endCell, countCell, minCell, enabledCell);
    return row;
}

const DEFAULT_SHIFT_TIMES = {
    Opening: { start: "08:00", end: "16:00" },
    Mid: { start: "12:00", end: "20:00" },
    Closing: { start: "14:00", end: "22:00" },
};

function getDefaultShiftTimes(shiftType) {
    return DEFAULT_SHIFT_TIMES[shiftType] || { start: "08:00", end: "16:00" };
}

function createShiftRow(shift) {
    const defaults = getDefaultShiftTimes(shift.shift_type);
    const startValue = (shift.start_time || "").slice(0, 5) || defaults.start;
    const endValue = (shift.end_time || "").slice(0, 5) || defaults.end;

    const row = document.createElement("tr");
    row.dataset.stationId = String(shift.station_id);
    row.dataset.shiftType = shift.shift_type;

    const nameCell = document.createElement("td");
    nameCell.textContent = shift.shift_type;

    const startCell = document.createElement("td");
    const startInput = document.createElement("input");
    startInput.className = "shift-config-input";
    startInput.type = "time";
    startInput.required = true;
    startInput.value = startValue;
    startInput.setAttribute("aria-label", `${shift.station_name} ${shift.shift_type} start time`);
    startCell.append(startInput);

    const endCell = document.createElement("td");
    const endInput = document.createElement("input");
    endInput.className = "shift-config-input";
    endInput.type = "time";
    endInput.required = true;
    endInput.value = endValue;
    endInput.setAttribute("aria-label", `${shift.station_name} ${shift.shift_type} end time`);
    endCell.append(endInput);

    const countCell = document.createElement("td");
    const countInput = document.createElement("input");
    countInput.className = "requirement-count-input";
    countInput.type = "number";
    countInput.min = "0";
    countInput.max = "100";
    countInput.step = "1";
    countInput.required = true;
    countInput.value = String(shift.required_count ?? 1);
    countInput.setAttribute("aria-label", `${shift.station_name} ${shift.shift_type} required crew`);
    countCell.append(countInput);

    const enabledCell = document.createElement("td");
    const enabledInput = document.createElement("input");
    enabledInput.className = "shift-enabled-input";
    enabledInput.type = "checkbox";
    enabledInput.checked = shift.enabled !== false;
    enabledInput.setAttribute(
        "aria-label",
        `${shift.station_name} ${shift.shift_type} shift enabled`,
    );

    const toggleShiftInputs = () => {
        const enabled = enabledInput.checked;
        startInput.disabled = !enabled;
        endInput.disabled = !enabled;
        countInput.disabled = !enabled;
        row.classList.toggle("staffing-shift-disabled", !enabled);
    };
    enabledInput.addEventListener("change", toggleShiftInputs);
    toggleShiftInputs();

    enabledCell.append(enabledInput);
    row.classList.toggle("staffing-shift-disabled", !enabledInput.checked);

    row.append(nameCell, startCell, endCell, countCell, enabledCell);
    return row;
}

function applyShiftTimesToAll(sourceStationId) {
    const sourceRows = tableBody.querySelectorAll(
        `tr[data-station-id="${sourceStationId}"][data-shift-type]`
    );
    if (sourceRows.length === 0) return;

    // Read source station's shift times and enabled states.
    const sourceByShift = new Map();
    sourceRows.forEach(row => {
        const shiftType = row.dataset.shiftType;
        const timeInputs = row.querySelectorAll('input[type="time"]');
        const numberInputs = row.querySelectorAll('input[type="number"]');
        const enabledInput = row.querySelector(".shift-enabled-input");
        sourceByShift.set(shiftType, {
            start: timeInputs[0] ? timeInputs[0].value : "",
            end: timeInputs[1] ? timeInputs[1].value : "",
            required: numberInputs[0] ? numberInputs[0].value : "",
            minimum: numberInputs[1] ? numberInputs[1].value : "",
            enabled: enabledInput ? enabledInput.checked : true,
        });
    });

    // Apply to all other stations (preserve required crew count).
    const allRows = tableBody.querySelectorAll("tr[data-station-id][data-shift-type]");
    allRows.forEach(row => {
        const stationId = Number(row.dataset.stationId);
        if (stationId === sourceStationId) return;

        const shiftType = row.dataset.shiftType;
        const source = sourceByShift.get(shiftType);
        if (!source) return;

        const timeInputs = row.querySelectorAll('input[type="time"]');
        const numberInputs = row.querySelectorAll('input[type="number"]');
        const enabledInput = row.querySelector(".shift-enabled-input");

        if (timeInputs[0]) timeInputs[0].value = source.start;
        if (timeInputs[1]) timeInputs[1].value = source.end;
        if (numberInputs[1]) numberInputs[1].value = source.minimum;

        if (enabledInput && enabledInput.checked !== source.enabled) {
            enabledInput.checked = source.enabled;
            enabledInput.dispatchEvent(new Event("change"));
        }
    });

    showMessage("Shift hours copied to all stations. Click Save requirements to apply.", "success");
}

function readRequirementRows() {
    return Array.from(
        tableBody.querySelectorAll("tr[data-station-id][data-shift-type]"),
        row => {
            const startInput = row.querySelector('input[type="time"]');
            const endInput = row.querySelectorAll('input[type="time"]')[1];
            const countInputs = row.querySelectorAll('input[type="number"]');
            const enabledInput = row.querySelector(".shift-enabled-input");
            return {
                station_id: Number(row.dataset.stationId),
                shift_type: row.dataset.shiftType,
                start_time: normalizeTime(startInput ? startInput.value : ""),
                end_time: normalizeTime(endInput ? endInput.value : ""),
                required_count: Number(countInputs[0] ? countInputs[0].value : 1),
                minimum_crew: Number(countInputs[1] ? countInputs[1].value : countInputs[0] ? countInputs[0].value : 1),
                enabled: enabledInput ? enabledInput.checked : true,
            };
        },
    );
}

async function loadRequirements() {
    saveButton.disabled = true;
    try {
        const [requirements, stations] = await Promise.all([
            requestJson("/staffing-requirements/"),
            requestJson("/stations/"),
        ]);
        // Build priority map: station_id -> priority
        stationPriorities = new Map();
        (stations || []).forEach(s => {
            stationPriorities.set(s.id, s.priority ?? 2);
        });
        renderRequirements(requirements, stationPriorities);
    } catch (error) {
        showMessage(error.message);
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.textContent = "Unable to load staffing requirements.";
        row.append(cell);
        tableBody.replaceChildren(row);
    }
}

form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;

    const requirements = readRequirementRows();
    let minCrewError = null;
    let timeError = null;
    let countError = null;
    const stationNames = new Map();
    for (const row of tableBody.querySelectorAll("tr.staffing-station-row.compact")) {
        const nameEl = row.querySelector(".station-compact-name");
        stationNames.set(
            Number(row.dataset.stationId),
            nameEl ? nameEl.textContent.trim() : `Station ${row.dataset.stationId}`,
        );
    }
    requirements.forEach(requirement => {
        requirement.required_count = Number(requirement.required_count);
        requirement.minimum_crew = requirement.minimum_crew != null ? Number(requirement.minimum_crew) : requirement.required_count;
        const name = stationNames.get(requirement.station_id) || `Station ${requirement.station_id}`;

        // End time must be later than start time
        const startParts = requirement.start_time.split(":").map(Number);
        const endParts = requirement.end_time.split(":").map(Number);
        const startMinutes = startParts[0] * 60 + startParts[1];
        const endMinutes = endParts[0] * 60 + endParts[1];
        if (endMinutes <= startMinutes && !timeError) {
            timeError = `${name} ${requirement.shift_type}: ang oras tapos ay dapat mas huli kaysa sa oras simula.`;
        }

        // Required crew between 0 and 100
        if (requirement.required_count < 0 || requirement.required_count > 100 && !countError) {
            countError = `${name} ${requirement.shift_type}: ang required crew ay dapat nasa 0 hanggang 100.`;
        }

        if (requirement.minimum_crew > requirement.required_count && !minCrewError) {
            minCrewError = `${name} ${requirement.shift_type}: minimum crew cannot be greater than required crew.`;
        }
    });
    if (timeError) {
        showMessage(timeError, "error");
        saveButton.disabled = false;
        return;
    }
    if (countError) {
        showMessage(countError, "error");
        saveButton.disabled = false;
        return;
    }
    if (minCrewError) {
        showMessage(minCrewError, "error");
        saveButton.disabled = false;
        return;
    }

    // Client-side check: bawat station ay kailangang may o kusa ang isang enabled shift.
    const enabledByStation = new Map();
    const allStationIds = new Set();
    for (const req of requirements) {
        allStationIds.add(req.station_id);
        if (req.enabled) {
            const list = enabledByStation.get(req.station_id) || [];
            list.push(req.shift_type);
            enabledByStation.set(req.station_id, list);
        }
    }
    for (const stationId of allStationIds) {
        const enabledShifts = enabledByStation.get(stationId) || [];
        if (enabledShifts.length === 0) {
            const name = stationNames.get(stationId) || `Station ${stationId}`;
            showMessage(
                `Station "${name}": kailangang may o kusa ang isang enabled shift. Piliin o kusa bago i-save.`,
                "error",
            );
            saveButton.disabled = false;
            return;
        }
    }

    saveButton.disabled = true;
    try {
        const updated = await requestJson("/staffing-requirements/", {
            method: "PUT",
            body: JSON.stringify({ requirements }),
        });
        renderRequirements(updated, stationPriorities);
        showMessage("Staffing requirements saved.", "success");
    } catch (error) {
        showMessage(error.message);
        saveButton.disabled = false;
    }
});

loadRequirements();

// Search filter for stations
let stationSearchFilter = "";
const stationSearchInput = document.getElementById("stationSearch");
if (stationSearchInput) {
    stationSearchInput.addEventListener("input", (e) => {
        stationSearchFilter = e.target.value.toLowerCase().trim();
        filterStationsBySearch();
    });
}

function filterStationsBySearch() {
    const rows = tableBody.querySelectorAll(".staffing-station-row.compact");
    const categoryRows = tableBody.querySelectorAll(".staffing-category-row");

    // Track which categories have at least one visible station
    const visibleCategories = new Set();

    rows.forEach(row => {
        const name = row.dataset.stationName || "";
        const matches = name.includes(stationSearchFilter);
        row.hidden = !matches;
        if (matches) {
            const cat = row.dataset.category;
            if (cat) visibleCategories.add(cat);
        }
    });

    categoryRows.forEach(row => {
        const cat = row.dataset.category;
        row.hidden = cat && !visibleCategories.has(cat);
    });
}

// Expand all / Collapse all
const expandAllBtn = document.getElementById("expandAllStations");
const collapseAllBtn = document.getElementById("collapseAllStations");
if (expandAllBtn) {
    expandAllBtn.addEventListener("click", () => {
        document.querySelectorAll(".station-inline-editor").forEach(ed => {
            ed.hidden = false;
        });
        document.querySelectorAll(".category-toggle").forEach(btn => {
            btn.setAttribute("aria-expanded", "true");
            btn.classList.remove("is-collapsed");
        });
        document.querySelectorAll(".staffing-station-row").forEach(row => {
            row.hidden = false;
        });
    });
}
if (collapseAllBtn) {
    collapseAllBtn.addEventListener("click", () => {
        document.querySelectorAll(".station-inline-editor").forEach(ed => {
            ed.hidden = true;
        });
        document.querySelectorAll(".category-toggle").forEach(btn => {
            btn.setAttribute("aria-expanded", "false");
            btn.classList.add("is-collapsed");
        });
    });
}
