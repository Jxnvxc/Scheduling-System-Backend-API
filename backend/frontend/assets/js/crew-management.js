const API_URL = window.SMARTSHIFT_API_URL;
const token = sessionStorage.getItem("access_token");
const crewForm = document.getElementById("crewForm");
const crewList = document.getElementById("crew-list");
const crewMessage = document.getElementById("crewMessage");
const crewCount = document.getElementById("crewCount");
const addCrewButton = document.getElementById("addCrewButton");
let user = null;
let branchStations = [];
let crewHoursById = {};

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
    crewMessage.textContent = message;
    crewMessage.className = `crew-message${message ? " is-visible" : ""}${type ? ` is-${type}` : ""}`;
}

function showEmptyState(title, message) {
    const state = document.createElement("div");
    state.className = "empty-state";
    const heading = document.createElement("strong");
    heading.textContent = title;
    state.append(heading, document.createTextNode(message));
    crewList.replaceChildren(state);
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
        throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
    }
    return data;
}

async function loadBranchAndStations() {
    const branchName = document.getElementById("assignedBranchName");
    const stationsContainer = document.getElementById("stations-checkboxes");
    try {
        const branches = await requestJson("/branches/");
        if (branches.length !== 1) {
            throw new Error("No branch is assigned to this manager account.");
        }
        branchName.textContent = branches[0].name;

        const stations = await requestJson("/stations/");
        branchStations = stations;
        stationsContainer.replaceChildren();
        if (stations.length === 0) {
            stationsContainer.textContent = "Wala pang stations sa branch na ito.";
            return;
        }

        stations.forEach(station => {
            const label = document.createElement("label");
            label.className = "choice-chip";
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "station-cb";
            checkbox.value = station.id;
            label.append(checkbox, document.createTextNode(station.name));
            stationsContainer.append(label);
        });
    } catch (error) {
        branchName.textContent = "Hindi ma-load ang branch";
        stationsContainer.textContent = error.message;
        addCrewButton.disabled = true;
        showMessage(`Hindi na-load ang branch information: ${error.message}`, "error");
    }
}

function renderCrew(crew) {
    crewCount.textContent = `${crew.length} ${crew.length === 1 ? "crew member" : "crew members"}`;
    if (crew.length === 0) {
        showEmptyState("Wala pang crew.", "Magdagdag ng unang crew member gamit ang form sa itaas.");
        return;
    }

    const crewTypes = ["Production crew", "Service crew", "Crew Trainer", "Maintenance crew", "Gel crew"];
    const crewByType = {};
    crewTypes.forEach(t => crewByType[t] = []);

    crew.forEach(member => {
        const types = String(member.crew_type || "")
            .split(",")
            .map(t => t.trim())
            .filter(Boolean);
        if (types.length === 0) {
            crewByType["Unassigned"].push(member);
        } else {
            types.forEach(t => {
                if (crewByType[t]) crewByType[t].push(member);
            });
        }
    });

    const container = document.createElement("div");
    container.className = "crew-tables-container";

Object.entries(crewByType).forEach(([type, members]) => {
            if (members.length === 0) return;
            const table = document.createElement("table");
            table.className = "crew-table";
            const thead = document.createElement("thead");
            thead.innerHTML = `
                <tr>
                    <th scope="col">Crew member</th>
                    <th scope="col">Email</th>
                    <th scope="col">Employee ID</th>
                    <th scope="col">Employment</th>
                    <th scope="col">Hours this cycle</th>
                    <th scope="col">Qualified stations</th>
                    <th scope="col">Actions</th>
                </tr>`;
            table.append(thead);

            const tbody = document.createElement("tbody");
            members.forEach(member => {
                const row = document.createElement("tr");
                row.innerHTML = `
                    <td class="crew-member-name">${escapeHtml(member.full_name)}</td>
                    <td class="crew-email">${escapeHtml(member.email)}</td>
                    <td>
                        <form class="employee-id-form" data-crew-id="${member.id}">
                            <input
                                aria-label="Employee ID para kay ${escapeHtml(member.full_name)}"
                                name="employee_id"
                                inputmode="numeric"
                                pattern="[0-9]+"
                                maxlength="32"
                                autocomplete="off"
                                required
                                value="${escapeHtml(member.employee_number || "")}"
                                placeholder="Ilagay ang ID"
                            />
                            <button type="submit">Save ID</button>
                        </form>
                    </td>
                    <td>${escapeHtml(member.employment_type || "—")}</td>
                    <td class="crew-hours">${Number(crewHoursById[member.id] ?? member.worked_hours ?? 0).toFixed(1)} hrs</td>
                    ${renderQualifiedStationsCell(member)}
                    <td>
                        <button type="button" class="delete-crew-button" data-delete-crew-id="${member.id}">Remove</button>
                    </td>`;
                tbody.append(row);
            });
            table.append(tbody);

            const wrapper = document.createElement("div");
            wrapper.className = "crew-type-table-wrapper";
            const heading = document.createElement("h3");
            heading.className = "crew-type-heading";
            heading.textContent = `${type} (${members.length})`;
            wrapper.append(heading, table);
            container.append(wrapper);
        });

    crewList.replaceChildren(container);
}

function renderQualifiedStationsCell(member) {
    const selectedIds = new Set(
        String(member.qualified_stations || "")
            .split(",")
            .map(value => value.trim())
            .filter(Boolean),
    );
    const selectedCount = branchStations.filter(
        station => selectedIds.has(String(station.id)),
    ).length;
    const options = branchStations.length
        ? branchStations.map(station => `
            <label class="crew-skill-option">
              <input
                type="checkbox"
                name="station_ids"
                value="${station.id}"
                ${selectedIds.has(String(station.id)) ? "checked" : ""}
              />
              <span>${escapeHtml(station.name)}</span>
            </label>
          `).join("")
        : '<span class="field-help">Walang station sa branch na ito.</span>';
    return `
      <td>
        <form class="qualified-stations-form" data-crew-id="${member.id}">
          <details class="crew-skills-dropdown">
            <summary>${selectedCount} ${selectedCount === 1 ? "station" : "stations"}</summary>
            <div class="crew-skills-options">${options}</div>
            <button type="submit" ${branchStations.length ? "" : "disabled"}>Save skills</button>
          </details>
        </form>
      </td>`;
}

async function loadHoursSummary() {
    const cycleRange = document.getElementById("crewCycleRange");
    try {
        const data = await requestJson("/crew/hours-summary");
        if (cycleRange) {
            cycleRange.textContent = data.period_label || "Loading...";
        }
        crewHoursById = {};
        (data.crew || []).forEach(member => {
            if (member.id != null) crewHoursById[member.id] = member.worked_hours;
        });
    } catch (error) {
        if (cycleRange) cycleRange.textContent = "unavailable";
        console.error("Could not load crew hours summary.", error);
    }
}

async function loadCrew() {
    crewList.innerHTML = '<div class="empty-state">Loading crew members...</div>';
    try {
        renderCrew(await requestJson("/crew/"));
    } catch (error) {
        crewCount.textContent = "Unavailable";
        showEmptyState("Hindi ma-load ang crew list.", error.message);
        showMessage(`Hindi ma-load ang crew: ${error.message}`, "error");
    }
}

async function addCrew(event) {
    event.preventDefault();

    const minHours = Number(document.getElementById("min_hours").value);
    const maxHours = Number(document.getElementById("max_hours").value);
    if (minHours > maxHours) {
        showMessage("Hindi puwedeng mas mataas ang minimum hours kaysa maximum hours.", "error");
        return;
    }

    const payload = {
        full_name: document.getElementById("crew_name").value.trim(),
        email: document.getElementById("crew_email").value.trim(),
        employee_number: document.getElementById("crew_employee_number").value.trim(),
        employment_type: document.getElementById("employment_type").value,
        crew_type: Array.from(document.querySelectorAll(".crew-type-cb:checked"))
            .map(input => input.value)
            .join(", ") || "Unassigned",
        min_hours: minHours,
        max_hours: maxHours,
        qualified_stations: Array.from(document.querySelectorAll(".station-cb:checked"))
            .map(input => input.value)
            .join(",") || null
    };

    addCrewButton.disabled = true;
    showMessage("Ginagawa ang crew account...");
    try {
        const member = await requestJson("/crew/", {
            method: "POST",
            body: JSON.stringify(payload)
        });
        crewForm.reset();
        showMessage(
            `Nagawa na ang account ni ${member.full_name}. Ibigay nang pribado ang initial password at ipapalit ito agad pagkatapos mag-sign in.`,
            "success"
        );
        await loadCrew();
    } catch (error) {
        showMessage(`Hindi nagawa ang crew account: ${error.message}`, "error");
    } finally {
        addCrewButton.disabled = false;
    }
}

async function saveEmployeeId(form) {
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    showMessage("Sine-save ang Employee ID...");
    try {
        await requestJson(`/crew/${form.dataset.crewId}/employee-number`, {
            method: "PUT",
            body: JSON.stringify({
                employee_number: form.elements.employee_id.value.trim()
            })
        });
        showMessage("Na-save na ang Employee ID.", "success");
        await loadCrew();
    } catch (error) {
        showMessage(`Hindi na-save ang Employee ID: ${error.message}`, "error");
        button.disabled = false;
    }
}

async function saveQualifiedStations(form) {
    const button = form.querySelector('button[type="submit"]');
    const stationIds = Array.from(
        form.querySelectorAll('input[name="station_ids"]:checked'),
        input => Number(input.value),
    );
    button.disabled = true;
    showMessage("Sine-save ang qualified stations...");
    try {
        await requestJson(`/crew/${form.dataset.crewId}/qualified-stations`, {
            method: "PUT",
            body: JSON.stringify({ station_ids: stationIds }),
        });
        showMessage("Na-update na ang qualified stations.", "success");
        await loadCrew();
    } catch (error) {
        showMessage(`Hindi na-update ang qualified stations: ${error.message}`, "error");
        button.disabled = false;
    }
}

async function removeCrew(memberId) {
    if (!window.confirm("Sigurado ka bang aalisin ang crew member na ito?")) return;
    try {
        await requestJson(`/crew/${memberId}`, { method: "DELETE" });
        showMessage("Naalis na ang crew member.", "success");
        await loadCrew();
    } catch (error) {
        showMessage(`Hindi naalis ang crew member: ${error.message}`, "error");
    }
}

function logout() {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    window.location.href = "index.html";
}

try {
    user = JSON.parse(sessionStorage.getItem("user"));
} catch (error) {
    console.error("Invalid user data in localStorage.", error);
}

if (!token || !user) {
    window.location.href = "index.html";
} else if (user.role !== "manager") {
    window.location.href = user.role === "head" ? "head-dashboard.html" : "dashboard.html";
} else {
    document.getElementById("userName").textContent = user.full_name;
    document.getElementById("topBarName").textContent = user.full_name;
    document.getElementById("userRole").textContent = user.role === "manager" ? "Manager" : "Crew";
    crewForm.addEventListener("submit", addCrew);

    const bulkAvailBtn = document.getElementById("bulkAvailBtn");
    const downloadTemplateBtn = document.getElementById("downloadTemplateBtn");
    const bulkAvailText = document.getElementById("bulkAvailText");
    const bulkAvailMessage = document.getElementById("bulkAvailMessage");

    if (bulkAvailBtn) {
        bulkAvailBtn.addEventListener("click", async () => {
            const text = bulkAvailText.value.trim();
            if (!text) {
                bulkAvailMessage.textContent = "Please paste availability data first.";
                bulkAvailMessage.className = "status-message is-error";
                return;
            }

            bulkAvailBtn.disabled = true;
            bulkAvailBtn.textContent = "Importing...";
            bulkAvailMessage.textContent = "Importing availability...";
            bulkAvailMessage.className = "status-message";

            try {
                const response = await fetch(`${API_URL}/availability/bulk-import`, {
                    method: "POST",
                    headers: {
                        Authorization: `Bearer ${token}`,
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ text }),
                });

                const data = await response.json();

                if (response.ok) {
                    let msg = `✅ Import complete: ${data.created} created, ${data.updated} updated`;
                    if (data.errors.length > 0) {
                        msg += `, ${data.errors.length} errors`;
                    }
                    bulkAvailMessage.textContent = msg;
                    bulkAvailMessage.className = data.errors.length ? "status-message is-error" : "status-message is-success";
                    if (data.errors.length > 0) {
                        bulkAvailMessage.textContent += "\nErrors:\n" + data.errors.join("\n");
                    }
                    bulkAvailText.value = "";
                } else {
                    const detail = data.detail;
                    let err;
                    if (Array.isArray(detail)) {
                        err = detail
                            .map(item => {
                                const loc = Array.isArray(item.loc) ? item.loc.join(".") : "";
                                return loc ? `${loc}: ${item.msg}` : item.msg;
                            })
                            .join("\n");
                    } else if (typeof detail === "string") {
                        err = detail;
                    } else if (detail != null) {
                        err = JSON.stringify(detail);
                    } else {
                        err = "Import failed";
                    }
                    bulkAvailMessage.textContent = "❌ " + err;
                    bulkAvailMessage.className = "status-message is-error";
                }
            } catch (error) {
                bulkAvailMessage.textContent = "❌ Error: " + (error.message || JSON.stringify(error));
                bulkAvailMessage.className = "status-message is-error";
            } finally {
                bulkAvailBtn.disabled = false;
                bulkAvailBtn.textContent = "Import Availability";
            }
        });
    }

    if (downloadTemplateBtn) {
        downloadTemplateBtn.addEventListener("click", () => {
            const csv = "employee_number,day_of_week,start_time,end_time,valid_from,valid_to\nEMP001,Monday,08:00,16:00,2024-01-01,2024-12-31\nEMP002,Tuesday,09:00,17:00,2024-01-01,2024-12-31\nEMP003,Wednesday,10:00,18:00,2024-01-01,2024-12-31";
            const blob = new Blob([csv], { type: "text/csv" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "availability_template.csv";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        });
    }
    crewList.addEventListener("submit", event => {
        const form = event.target.closest(".employee-id-form, .qualified-stations-form");
        if (!form) return;
        event.preventDefault();
        if (form.matches(".qualified-stations-form")) {
            saveQualifiedStations(form);
        } else {
            saveEmployeeId(form);
        }
    });
    crewList.addEventListener("click", event => {
        const button = event.target.closest("[data-delete-crew-id]");
        if (button) removeCrew(button.dataset.deleteCrewId);
    });
    document.getElementById("logoutButton").addEventListener("click", logout);
    loadBranchAndStations().finally(() => loadHoursSummary().then(loadCrew));

    const resetButton = document.getElementById("reset15DayHoursButton");
    if (resetButton) {
        resetButton.addEventListener("click", async () => {
            if (!window.confirm("I-reset ang 15-day hours counter ng lahat ng crew sa inyong branch? Ang nakaraang schedule ay hindi ma-aalis.")) {
                return;
            }
            resetButton.disabled = true;
            resetButton.textContent = "Resetting...";
            try {
                const data = await requestJson("/crew/reset-15-day-hours", {
                    method: "POST",
                });
                showMessage(data.message || "Na-reset na ang 15-day hours counter.", "success");
                crewHoursById = {};
                renderCrew(await requestJson("/crew/"));
            } catch (error) {
                showMessage(`Hindi ma-reset ang oras: ${error.message}`, "error");
            } finally {
                resetButton.disabled = false;
                resetButton.textContent = "Reset 15-Day Hours";
            }
        });
    }
}
