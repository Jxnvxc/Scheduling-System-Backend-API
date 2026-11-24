const API_URL = window.SMARTSHIFT_API_URL;
const token = sessionStorage.getItem("access_token");
const userString = sessionStorage.getItem("user");

if (!token || !userString) window.location.href = "index.html";

let user = null;
try {
    user = JSON.parse(userString);
} catch (error) {
    console.error("Invalid user data in session storage.", error);
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    window.location.href = "index.html";
}

let currentWeekSchedule = [];   // array of {date, schedule} for Mon-Sun
let currentWeekStartDate = null; // the Monday of the generated week
let currentValidationIssues = [];
let draftValidationSequence = 0;
let draftIsValid = false;
let crewPeriodHoursById = {};    // published worked_hours per user for active 15-day period
let crewAssignedShiftsById = {}; // published assigned shifts per user for active 15-day period, keyed by user id (string)
let selectedDayFilter = "all";   // "all" or a weekday key (mon-sun)
let showShortagesOnly = false;   // when true, only shortage rows are visible

// 1. USER INFO & RBAC
if (user) {
    if (document.getElementById("userName")) document.getElementById("userName").textContent = user.full_name;
    if (document.getElementById("userRole")) document.getElementById("userRole").textContent = user.role === "employee" ? "Crew" : "Manager";
    if (document.getElementById("topBarName")) document.getElementById("topBarName").textContent = user.full_name;
}

function applyRolePermissions(role) {
    const managerOnly = document.querySelectorAll(".manager-only");
    const crewOnly = document.querySelectorAll(".crew-only");
    const managerActionOnly = document.querySelectorAll(".manager-action-only");

    if (role === "manager") {
        crewOnly.forEach(el => el.style.display = "none");
    } else if (role === "employee") {
        managerOnly.forEach(el => el.style.display = "none");
        managerActionOnly.forEach(el => el.style.display = "none");
        crewOnly.forEach(el => el.style.display = "");
    }
}
if (user && user.role) applyRolePermissions(user.role);

// 2. DATE INPUT (week start, max 7 days ahead)
function initDateInput() {
    const dateInput = document.getElementById("gen_week_start");
    if (!dateInput) return;

    const formatDate = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    };

    // Compute today in Asia/Manila using Intl.DateTimeFormat (no string parsing)
    const now = new Date();
    const manilaToday = new Date(now.toLocaleDateString("en-CA", { timeZone: "Asia/Manila" }));
    const maxDate = new Date(manilaToday);
    maxDate.setDate(manilaToday.getDate() + 7);

    // Monday = today - (weekday - 1), with Sunday(0) -> -6
    const monday = new Date(manilaToday);
    monday.setDate(manilaToday.getDate() - manilaToday.getDay() + (manilaToday.getDay() === 0 ? -6 : 1));

    dateInput.min = formatDate(monday);
    dateInput.max = formatDate(maxDate);
    dateInput.value = formatDate(monday);
}

function formatDateInput(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

initDateInput();

// 3. GENERATE SCHEDULE SUBMIT (runs inline in dashboard workspace)
document.getElementById("generateScheduleForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    currentWeekSchedule = [];
    currentWeekStartDate = null;
    draftIsValid = false;
    draftValidationSequence += 1;
    document.getElementById("publishScheduleButton").disabled = true;
    document.getElementById("saveDraftScheduleButton").disabled = true;
    document.getElementById("exportScheduleButton").disabled = true;
    document.getElementById("exportPdfScheduleButton").disabled = true;
    document.getElementById("exportDocxScheduleButton").disabled = true;
    document.getElementById("printScheduleButton").disabled = true;

    const date = document.getElementById("gen_week_start").value;

    // Validation - compute Manila today without locale-dependent parsing
    const now = new Date();
    const manilaToday = new Date(now.toLocaleDateString("en-CA", { timeZone: "Asia/Manila" }));
    manilaToday.setHours(0, 0, 0, 0);
    const maxDate = new Date(manilaToday); maxDate.setDate(manilaToday.getDate() + 7);
    const selectedDate = new Date(`${date}T00:00:00`);

    if (selectedDate > maxDate || selectedDate < manilaToday) {
        alert("❌ Bawal pumili ng petsa na lampas sa 7 araw o sa nakaraan!");
        return;
    }

    // Show loading state
    const genBtn = document.getElementById("genBtn");
    const genBtnText = document.getElementById("genBtnText");
    const genBtnSpinner = document.getElementById("genBtnSpinner");
    const resultDiv = document.getElementById("generateResult");
    const resultBody = document.getElementById("resultTableBody");
    const summaryCards = document.getElementById("summaryCards");
    const genError = document.getElementById("genError");

    genBtn.disabled = true;
    genBtnText.textContent = "Gumagawa ng schedule...";
    genBtnSpinner.style.display = "inline-block";
    resultDiv.style.display = "none";
    summaryCards.style.display = "none";
    genError.style.display = "none";

    try {
        const response = await fetch(`${API_URL}/schedules/generate-single-day`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                target_date: date,
                shift_name: "Closing"
            })
        });
        const data = await response.json();

        if (!response.ok) {
            genBtn.disabled = false;
            genBtnText.textContent = "Lagyan ng schedule";
            genBtnSpinner.style.display = "none";
            genError.textContent = data.detail || "Nagkamang magsimula ng pag-generate.";
            genError.style.display = "block";
            resultDiv.style.display = "none";
            return;
        }

        currentWeekSchedule = [data];
        currentWeekStartDate = date;
        selectedDayFilter = "all";
        document.getElementById("gen_week_start").disabled = true;
        document.getElementById("clearDraftAssignmentsButton").disabled = false;

        resultDiv.style.display = "block";
        resultBody.innerHTML = "";

        const sumData = buildSummaryFromData([data]);
        renderSummaryCards(sumData);
        renderShortageTab(sumData);
        renderHoursTab(sumData);
        renderSchedulePreview([data]);

        genBtn.disabled = false;
        genBtnText.textContent = "Lagyan ng schedule";
        genBtnSpinner.style.display = "none";

    } catch (err) {
        genBtn.disabled = false;
        genBtnText.textContent = "Lagyan ng schedule";
        genBtnSpinner.style.display = "none";
        genError.textContent = "Hindi makonekta sa server. Isubok muli.";
        genError.style.display = "block";
        resultDiv.style.display = "none";
    }});
let currentPollJobId = null;
let currentPollTimer = null;

window.cancelGeneration = function() {
    if (currentPollTimer) {
        clearInterval(currentPollTimer);
        currentPollTimer = null;
    }
    const btn = document.getElementById("genCancelBtn");
    if (btn) btn.style.display = "none";
    const genBtn = document.getElementById("genBtn");
    if (genBtn) {
        genBtn.disabled = false;
        const btnText = document.getElementById("genBtnText");
        if (btnText) btnText.textContent = "Lagyan ng schedule";
        const spinner = document.getElementById("genBtnSpinner");
        if (spinner) spinner.style.display = "none";
        const el = document.getElementById("genElapsed");
        if (el) el.textContent = "";
    }
    if (currentPollJobId) {
        fetch(`${API_URL}/schedules/generate-cancel/${currentPollJobId}`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` }
        }).catch(() => {});
        currentPollJobId = null;
    }
    const genError = document.getElementById("genError");
    if (genError) {
        genError.textContent = "In-cancel ang pag-generate.";
        genError.style.display = "block";
    }
    const resultDiv = document.getElementById("generateResult");
    if (resultDiv) resultDiv.style.display = "none";
};

// 4. RENDER COMPACT SCHEDULE TABLE (all 7 days)
function markDraftDirty() {
    draftIsValid = false;
    draftValidationSequence += 1;
    currentValidationIssues = [];
    const publishButton = document.getElementById("publishScheduleButton");
    const message = document.getElementById("publishValidationMessage");
    const details = document.getElementById("scheduleIssuesDetails");
    if (publishButton) publishButton.disabled = true;
    if (message) {
        message.classList.remove("is-valid", "is-error");
        message.textContent = "Draft changed. Run validation again before publishing.";
    }
    if (details) {
        details.style.display = "none";
        details.innerHTML = "";
    }
    const saveBtn = document.getElementById("saveDraftScheduleButton");
    if (saveBtn) {
        const hasAssignments = currentWeekSchedule.some(day =>
            Array.isArray(day?.schedule) && day.schedule.some(row => (row.assigned || []).length > 0)
        );
        saveBtn.disabled = !hasAssignments;
    }
}

function refreshRowCrewState(rowData, crewCell, coverageCell, countEl, badgeEl) {
    const dropdown = crewCell.querySelector(".qualified-dropdown");
    const pickBtn = crewCell.querySelector(".crew-pick-btn");
    crewCell.innerHTML = "";

    const assigned = rowData.assigned || [];
    if (assigned.length) {
        assigned.forEach(emp => {
            const badge = document.createElement("span");
            badge.className = "crew-badge";
            badge.textContent = emp.name;
            if (emp.crew_type) {
                const type = document.createElement("span");
                type.className = "crew-type";
                type.textContent = `(${emp.crew_type})`;
                badge.append(" ", type);
            }
            crewCell.append(badge);
        });
    } else {
        const empty = document.createElement("span");
        empty.className = "crew-empty";
        empty.textContent = "Unassigned";
        crewCell.append(empty);
    }

    if (pickBtn) crewCell.append(pickBtn);
    if (dropdown) crewCell.append(dropdown);

    const filled = assigned.length >= (rowData.needed || 0);
    rowData.status = filled ? "Complete" : "Shortage";
    if (countEl) countEl.textContent = `${assigned.length} / ${rowData.needed}`;
    if (badgeEl) {
        badgeEl.className = `coverage-badge ${filled ? "is-complete" : "is-shortage"}`;
        badgeEl.textContent = filled ? "Complete" : "Shortage";
    }
}

function parseShiftTimes(row) {
    const [startStr, endStr] = String(row.time || "").split(" - ");
    const toMinutes = (s) => {
        if (!s || !/^\d{1,2}:\d{2}$/.test(s.trim())) return null;
        const [h, m] = s.trim().split(":").map(Number);
        return h * 60 + m;
    };
    return { start: toMinutes(startStr), end: toMinutes(endStr) };
}

function shiftDurationHours(row) {
    const { start, end } = parseShiftTimes(row);
    if (start == null || end == null || end <= start) return 0;
    return (end - start) / 60;
}

function getPeriodHours(userId) {
    let total = crewPeriodHoursById[userId] || 0;
    currentWeekSchedule.forEach(day => {
        (day.schedule || []).forEach(row => {
            (row.assigned || []).forEach(emp => {
                if (emp.id === userId) total += shiftDurationHours(row);
            });
        });
    });
    return total;
}

function getDraftHoursForUser(userId) {
    let total = 0;
    currentWeekSchedule.forEach(day => {
        (day.schedule || []).forEach(row => {
            (row.assigned || []).forEach(emp => {
                if (emp.id === userId) total += shiftDurationHours(row);
            });
        });
    });
    return total;
}

function getDraftShiftsForUser(userId) {
    const shifts = [];
    currentWeekSchedule.forEach(day => {
        (day.schedule || []).forEach(row => {
            (row.assigned || []).forEach(emp => {
                if (emp.id === userId) {
                    const [startTime, endTime] = (row.time || "").split(" - ");
                    shifts.push({
                        schedule_date: day.date,
                        station: row.station,
                        shift_name: row.shift,
                        start_time: startTime,
                        end_time: endTime,
                    });
                }
            });
        });
    });
    return shifts;
}

function getCandidateStatus(candidate, targetRow, targetDate) {
    const { start: slotStart, end: slotEnd } = parseShiftTimes(targetRow);
    if (slotStart == null || slotEnd == null) return { available: false, reason: "Invalid shift time" };

    // Check overlapping assignment on the same day in current draft
    const day = currentWeekSchedule.find(d => d.date === targetDate);
    if (day) {
        for (const row of day.schedule || []) {
            if (row === targetRow) continue;
            if ((row.assigned || []).some(emp => emp.id === candidate.id)) {
                const { start: rStart, end: rEnd } = parseShiftTimes(row);
                if (rStart != null && rEnd != null && !(slotEnd <= rStart || slotStart >= rEnd)) {
                    return { available: false, reason: `Overlapping shift (${row.station} ${row.shift})` };
                }
            }
        }
    }

    // Strict availability check: entire shift must fall within crew's available window
    const availStart = candidate.available_start;
    const availEnd = candidate.available_end;
    if (availStart != null && availEnd != null) {
        const [availSh, availSm] = String(availStart).split(":").map(Number);
        const [availEh, availEm] = String(availEnd).split(":").map(Number);
        const availStartMin = availSh * 60 + availSm;
        const availEndMin = availEh * 60 + availEm;
        if (slotStart < availStartMin || slotEnd > availEndMin) {
            const availLabel = `${String(availSh).padStart(2, "0")}:${String(availSm).padStart(2, "0")} – ${String(availEh).padStart(2, "0")}:${String(availEm).padStart(2, "0")}`;
            return {
                available: false,
                reason: `Outside crew availability (Available: ${availLabel})`,
                outsideAvailability: true,
            };
        }
    }

    // 15-day period hours check (Min: 40h / Max: 80h)
    const currentHours = getPeriodHours(candidate.id);
    const slotHours = shiftDurationHours(targetRow);
    const alreadyInSlot = (targetRow.assigned || []).some(emp => emp.id === candidate.id);
    const projectedHours = alreadyInSlot ? currentHours : currentHours + slotHours;
    const maxHours = candidate.max_hours != null ? candidate.max_hours : 80;
    const minHours = candidate.min_hours != null ? candidate.min_hours : 40;
    if (!alreadyInSlot && projectedHours > maxHours) {
        return { available: false, reason: `Would exceed 15-day max hours (${projectedHours.toFixed(1)}/${maxHours})`, overMax: true };
    }

    // Flag whether this candidate is still below the 40-hour minimum (for manager prioritization)
    const belowMinimum = projectedHours < minHours;

    // 11-hour minimum rest check against other days in current draft
    const slotStartDt = new Date(`${targetDate}T${String(Math.floor(slotStart / 60)).padStart(2, "0")}:${String(slotStart % 60).padStart(2, "0")}:00`);
    const slotEndDt = new Date(`${targetDate}T${String(Math.floor(slotEnd / 60)).padStart(2, "0")}:${String(slotEnd % 60).padStart(2, "0")}:00`);
    for (const d of currentWeekSchedule) {
        for (const row of d.schedule || []) {
            if (row === targetRow) continue;
            if (!(row.assigned || []).some(emp => emp.id === candidate.id)) continue;
            const { start: rStart, end: rEnd } = parseShiftTimes(row);
            if (rStart == null || rEnd == null) continue;
            const rStartDt = new Date(`${d.date}T${String(Math.floor(rStart / 60)).padStart(2, "0")}:${String(rStart % 60).padStart(2, "0")}:00`);
            const rEndDt = new Date(`${d.date}T${String(Math.floor(rEnd / 60)).padStart(2, "0")}:${String(rEnd % 60).padStart(2, "0")}:00`);
            let restMs;
            if (rStartDt <= slotStartDt) restMs = slotStartDt - rEndDt;
            else restMs = rStartDt - slotEndDt;
            if (restMs < 11 * 60 * 60 * 1000) {
                return { available: false, reason: "Rest conflict (< 11 hours)" };
            }
        }
    }

    return { available: true, reason: "Available", hours: projectedHours, belowMinimum: belowMinimum };
}

function closeCrewPickerModal() {
    const modal = document.getElementById("crewPickerModal");
    if (modal) modal.remove();
}

function openCrewPickerModal(rowData, date, crewCell, coverageCell, countEl, badgeEl) {
    closeCrewPickerModal();
    const qualifiedCrew = rowData.qualified_crew || [];

    const modal = document.createElement("div");
    modal.id = "crewPickerModal";
    modal.className = "modal";
    modal.style.display = "flex";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");

    const content = document.createElement("div");
    content.className = "modal-content";
    content.style.width = "min(560px, 94%)";

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "modal-close";
    closeBtn.setAttribute("aria-label", "Close");
    closeBtn.textContent = "×";
    closeBtn.addEventListener("click", closeCrewPickerModal);

    const title = document.createElement("h2");
    title.textContent = "Choose crew";

    const sub = document.createElement("p");
    sub.style.cssText = "margin:0 0 12px;color:var(--text-muted);font-size:12px;";
    sub.textContent = `${rowData.station} · ${rowData.shift} · ${rowData.time} · ${date}`;

    const listWrap = document.createElement("div");
    listWrap.style.cssText = "max-height:360px;overflow-y:auto;border:1px solid var(--border-light);border-radius:8px;";

    const list = document.createElement("ul");
    list.style.cssText = "list-style:none;margin:0;padding:0;";

    // Unassign option
    const unLi = document.createElement("li");
    unLi.style.cssText = "padding:10px 12px;border-bottom:1px solid #edf2f1;";
    const unBtn = document.createElement("button");
    unBtn.type = "button";
    unBtn.className = "btn-secondary";
    unBtn.style.cssText = "width:100%;text-align:left;";
    unBtn.textContent = "Unassigned";
    unBtn.addEventListener("click", () => {
        rowData.assigned = [];
        refreshRowCrewState(rowData, crewCell, coverageCell, countEl, badgeEl);
        markDraftDirty();
        closeCrewPickerModal();
    });
    unLi.append(unBtn);
    list.append(unLi);

    // Sort: candidates whose availability fully covers the shift first,
    // then those below minimum hours, then alphabetically.
    const { start: slotStart, end: slotEnd } = parseShiftTimes(rowData);
    const sortedCrew = [...qualifiedCrew].sort((a, b) => {
        const fitsA = a.available_start != null && a.available_end != null
            ? (() => {
                const [ash, asm] = String(a.available_start).split(":").map(Number);
                const [ahe, aem] = String(a.available_end).split(":").map(Number);
                return slotStart >= ash * 60 + asm && slotEnd <= ahe * 60 + aem;
            })()
            : true;
        const fitsB = b.available_start != null && b.available_end != null
            ? (() => {
                const [bsh, bsm] = String(b.available_start).split(":").map(Number);
                const [bhe, bem] = String(b.available_end).split(":").map(Number);
                return slotStart >= bsh * 60 + bsm && slotEnd <= bhe * 60 + bem;
            })()
            : true;
        if (fitsA === fitsB) return 0;
        return fitsA ? -1 : 1;
    });

    sortedCrew.forEach(candidate => {
        const status = getCandidateStatus(candidate, rowData, date);
        const publishedHours = Number(crewPeriodHoursById[String(candidate.id)] || 0);
        const draftHours = getDraftHoursForUser(candidate.id);
        const projected = publishedHours + draftHours;
        const minHours = candidate.min_hours != null ? candidate.min_hours : 40;
        const maxHours = candidate.max_hours != null ? candidate.max_hours : 80;
        const belowMinimum = projected < minHours;
        const isOverMax = status.overMax === true;
        const outsideAvailability = status.outsideAvailability === true;
        const li = document.createElement("li");
        li.style.cssText = "padding:10px 12px;border-bottom:1px solid #edf2f1;display:flex;align-items:center;justify-content:space-between;gap:10px;";

        const info = document.createElement("div");
        const name = document.createElement("div");
        name.style.fontWeight = "600";
        name.textContent = candidate.crew_type ? `${candidate.name} (${candidate.crew_type})` : candidate.name;

        const shiftsList = document.createElement("div");
        shiftsList.style.cssText = "font-size:10.5px;color:var(--text-muted);margin-top:4px;line-height:1.4;";
        const assignedShifts = crewAssignedShiftsById[String(candidate.id)] || [];
        const draftAssignedShifts = getDraftShiftsForUser(candidate.id);
        if (assignedShifts.length === 0 && draftAssignedShifts.length === 0) {
            shiftsList.textContent = `No assigned shifts yet (0.0 / ${maxHours.toFixed(0)} hrs)`;
        } else {
            const lines = [];
            if (publishedHours > 0) {
                lines.push(`Published: ${publishedHours.toFixed(1)} / ${maxHours.toFixed(0)} hrs`);
                assignedShifts.forEach(s => {
                    const dayLabel = new Date(`${s.schedule_date}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
                    const startFmt = s.start_time ? String(s.start_time).slice(0, 5) : "--:--";
                    const endFmt = s.end_time ? String(s.end_time).slice(0, 5) : "--:--";
                    lines.push(`  ${dayLabel}: ${s.station} ${s.shift_name} (${startFmt}–${endFmt})`);
                });
            }
            if (draftHours > 0) {
                lines.push(`This draft: ${draftHours.toFixed(1)} hrs`);
                draftAssignedShifts.forEach(s => {
                    const dayLabel = new Date(`${s.schedule_date}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
                    const startFmt = s.start_time ? String(s.start_time).slice(0, 5) : "--:--";
                    const endFmt = s.end_time ? String(s.end_time).slice(0, 5) : "--:--";
                    lines.push(`  ${dayLabel}: ${s.station} ${s.shift_name} (${startFmt}–${endFmt}) [draft]`);
                });
            }
            shiftsList.textContent = lines.join("\n");
        }

        const meta = document.createElement("div");
        meta.style.cssText = "font-size:11px;margin-top:2px;";
        const availLabel = candidate.available_start != null && candidate.available_end != null
            ? ` | Avail: ${String(candidate.available_start).slice(0, 5)} – ${String(candidate.available_end).slice(0, 5)}`
            : "";
        const hoursLabel = belowMinimum
            ? `${projected.toFixed(1)} / ${maxHours.toFixed(0)} hrs this 15-day period (Min: 40h, below min)`
            : `${projected.toFixed(1)} / ${maxHours.toFixed(0)} hrs this 15-day period (Min: 40h)`;
        meta.textContent = `${hoursLabel}${availLabel} · ${status.reason}`;
        meta.style.color = isOverMax ? "#b42318" : (outsideAvailability ? "#b42318" : (belowMinimum ? "#9a6a00" : "#1f6f43"));
        info.append(name, shiftsList, meta);

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = status.available ? "btn-primary" : "btn-secondary";
        btn.textContent = status.available ? "Assign" : "Assign anyway";
        btn.style.cssText = "font-size:12px;padding:6px 10px;white-space:nowrap;";
        btn.addEventListener("click", () => {
            rowData.assigned = [{
                id: candidate.id,
                name: candidate.name,
                crew_type: candidate.crew_type || null,
            }];
            refreshRowCrewState(rowData, crewCell, coverageCell, countEl, badgeEl);
            markDraftDirty();
            closeCrewPickerModal();
        });

        li.append(info, btn);
        list.append(li);
    });

    listWrap.append(list);
    content.append(closeBtn, title, sub, listWrap);
    modal.append(content);
    modal.addEventListener("click", (e) => { if (e.target === modal) closeCrewPickerModal(); });
    document.body.append(modal);
}

function renderSchedulePreview(weekSchedule) {
    const resultBody = document.getElementById("resultTableBody");
    const details = document.getElementById("schedulePreviewDetails");
    const branchName = document.getElementById("assignedBranchName")?.textContent;
    const start = currentWeekStartDate;
    details.textContent = `${branchName && branchName !== "Loading branch..." ? branchName : "Assigned branch"} · ${new Date(`${start}T00:00:00`).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })}`;

    const formatClock = value => {
        if (typeof value !== "string" || !/^\d{1,2}:\d{2}$/.test(value)) {
            return "Time unavailable";
        }
        const [hour, minute] = value.split(":").map(Number);
        const period = hour >= 12 ? "PM" : "AM";
        return `${hour % 12 || 12}:${String(minute).padStart(2, "0")} ${period}`;
    };

    const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const dayKeyByName = { sun: "sun", mon: "mon", tue: "tue", wed: "wed", thu: "thu", fri: "fri", sat: "sat" };
    const fragment = document.createDocumentFragment();

    // Show day navigation and populate with actual dates
    const dayNav = document.getElementById("scheduleDayNav");
    if (dayNav) {
        dayNav.style.display = "flex";
        const dayButtons = dayNav.querySelectorAll(".day-tab");
        dayButtons.forEach(btn => {
            btn.classList.remove("active");
            if (btn.dataset.day === "all") btn.classList.add("active");
        });
    }

    weekSchedule.forEach((day) => {
        if (!day || !Array.isArray(day.schedule) || day.schedule.length === 0) return;
        const dayDate = new Date(`${day.date}T00:00:00`);
        const dayKey = dayNames[dayDate.getDay()].toLowerCase();
        const dayHeader = document.createElement("tr");
        dayHeader.className = "schedule-day-header";
        dayHeader.dataset.day = dayKey;
        const headerCell = document.createElement("td");
        headerCell.colSpan = 5;
        const holiday = getHolidayForDate(day.date);
        const dateStr = dayDate.toLocaleDateString(undefined, { month: "short", day: "numeric" });
        const holidayLabel = holiday
            ? ` · <span class="holiday-label">Holiday: ${holiday.name}</span>`
            : "";
        headerCell.innerHTML = `${dayNames[dayDate.getDay()]} · ${dateStr}${holidayLabel}`;
        if (holiday) dayHeader.classList.add("is-holiday");
        dayHeader.append(headerCell);
        fragment.append(dayHeader);

        const entries = day.schedule.map(row => {
            const [startTime] = row.time.split(" - ");
            const [startHour, startMinute] = startTime.split(":").map(Number);
            return { row, startMinutes: startHour * 60 + startMinute };
        }).sort((left, right) =>
            left.row.station.localeCompare(right.row.station)
            || left.row.station_id - right.row.station_id
            || left.startMinutes - right.startMinutes
        );

        entries.forEach(({ row: r }) => {
            const [startTime, endTime] = r.time.split(" - ");
            const tableRow = document.createElement("tr");
            tableRow.dataset.stationId = r.station_id;
            tableRow.dataset.station = r.station;
            tableRow.dataset.shift = r.shift;
            tableRow.dataset.date = day.date;
            tableRow.dataset.day = dayKey;

            const stationCell = document.createElement("td");
            stationCell.className = "schedule-station-cell";
            stationCell.textContent = r.station;
            tableRow.append(stationCell);

            const shiftCell = document.createElement("td");
            shiftCell.className = "schedule-time-cell";
            shiftCell.textContent = `${r.shift} · ${formatClock(startTime)} - ${formatClock(endTime)}`;
            tableRow.append(shiftCell);

            const crewCell = document.createElement("td");
            crewCell.className = "schedule-crew-cell";
            const assigned = r.assigned || [];
            if (assigned.length) {
                assigned.forEach(emp => {
                    const badge = document.createElement("span");
                    badge.className = "crew-badge";
                    badge.textContent = emp.name;
                    if (emp.is_mirrored) {
                        badge.classList.add(r.mirror_conflict_reason ? "is-mirrored-flagged" : "is-mirrored");
                        badge.title = r.mirror_conflict_reason || "Mirrored from pre-holiday schedule";
                    }
                    if (emp.crew_type) {
                        const type = document.createElement("span");
                        type.className = "crew-type";
                        type.textContent = `(${emp.crew_type})`;
                        badge.append(" ", type);
                    }
                    crewCell.append(badge);
                });
            } else {
                const empty = document.createElement("span");
                empty.className = "crew-empty";
                empty.textContent = "Unassigned";
                crewCell.append(empty);
            }

            const qualifiedCrew = r.qualified_crew || [];
            const pickBtn = document.createElement("button");
            pickBtn.type = "button";
            pickBtn.className = "crew-pick-btn";
            pickBtn.textContent = qualifiedCrew.length ? "Choose crew" : "No candidates";
            pickBtn.disabled = !qualifiedCrew.length;
            pickBtn.setAttribute("aria-label", "Qualified crew candidates");
            pickBtn.dataset.date = day.date;
            pickBtn.dataset.stationId = String(r.station_id);
            pickBtn.dataset.shift = r.shift;
            crewCell.append(pickBtn);

            tableRow.append(crewCell);

            const coverageCell = document.createElement("td");
            coverageCell.className = "schedule-coverage-cell";
            const count = document.createElement("span");
            count.className = "coverage-count";
            count.textContent = `${assigned.length} / ${r.needed}`;
            const isComplete = assigned.length >= (r.needed || 0);
            const badge = document.createElement("span");
            badge.className = `coverage-badge ${isComplete ? "is-complete" : "is-shortage"}`;
            badge.textContent = isComplete ? "Complete" : "Shortage";
            coverageCell.append(count, " ", badge);
            tableRow.append(coverageCell);

            tableRow.dataset.shortage = isComplete ? "false" : "true";

            const qualifiedCell = document.createElement("td");
            qualifiedCell.className = "schedule-qualified-col";
            qualifiedCell.textContent = qualifiedCrew.length;
            tableRow.append(qualifiedCell);

            fragment.append(tableRow);
        });
    });

    resultBody.replaceChildren(fragment);

    // Understaffed summary banner
    let totalFilled = 0;
    let totalRequired = 0;
    let totalShortage = 0;
    let totalMinimumMissing = 0;
    const allUnfilled = [];
    weekSchedule.forEach(day => {
        (day.schedule || []).forEach(row => {
            totalRequired += row.needed || 0;
            totalFilled += (row.assigned || []).length;
            if ((row.assigned || []).length < (row.needed || 0)) {
                totalShortage += (row.needed || 0) - (row.assigned || []).length;
            }
        });
        (day.unfilled || []).forEach(u => {
            allUnfilled.push({ date: day.date, ...u });
            if (!u.minimum_met) totalMinimumMissing++;
        });
    });

    const banner = document.getElementById("understaffedBanner");
    const countEl = document.getElementById("understaffedCount");
    const shortageEl = document.getElementById("understaffedShortage");
    const unfilledList = document.getElementById("unfilledSlotsList");
    const unfilledItems = document.getElementById("unfilledSlotsItems");
    if (banner && countEl && shortageEl) {
        if (totalShortage > 0) {
            banner.style.display = "flex";
            countEl.textContent = `${totalFilled} / ${totalRequired} slots filled`;
            shortageEl.textContent = `• ${totalShortage} shortage${totalShortage !== 1 ? "s" : ""}`;
            // Color code: red if any minimum crew missed, yellow if only ideal missed
            if (totalMinimumMissing > 0) {
                banner.classList.add("understaffed-banner-critical");
                banner.classList.remove("understaffed-banner-warning");
            } else {
                banner.classList.add("understaffed-banner-warning");
                banner.classList.remove("understaffed-banner-critical");
            }
        } else {
            banner.style.display = "none";
            banner.classList.remove("understaffed-banner-warning", "understaffed-banner-critical");
        }
    }

    // Populate expandable unfilled slots list
    if (unfilledList && unfilledItems) {
        if (allUnfilled.length > 0) {
            unfilledList.style.display = "block";
            unfilledItems.replaceChildren();
            allUnfilled.forEach(u => {
                const li = document.createElement("li");
                li.className = "unfilled-slot-item";
                const minimumTag = u.minimum_met ? "" : ` <span class="unfilled-minimum-tag">MINIMUM MISSED</span>`;
                const priorityTag = u.priority ? ` <span class="unfilled-priority-tag">P${u.priority}</span>` : "";
                // Build breakdown tooltip
                let breakdownHtml = "";
                if (u.breakdown) {
                    const parts = [];
                    if (u.breakdown.not_available) parts.push(`<span class="bd-na">Not available: ${u.breakdown.not_available}</span>`);
                    if (u.breakdown.already_assigned_today) parts.push(`<span class="bd-aa">Already assigned today: ${u.breakdown.already_assigned_today}</span>`);
                    if (u.breakdown.max_hours) parts.push(`<span class="bd-mh">Max hours: ${u.breakdown.max_hours}</span>`);
                    if (u.breakdown.rest_rule) parts.push(`<span class="bd-rr">11hr rest: ${u.breakdown.rest_rule}</span>`);
                    if (u.breakdown.other) parts.push(`<span class="bd-other">Other: ${u.breakdown.other}</span>`);
                    if (parts.length) breakdownHtml = `<div class="unfilled-breakdown">${parts.join(" · ")}</div>`;
                }
                li.innerHTML = `
                    <strong>${u.station}</strong> · ${u.shift} · ${new Date(`${u.date}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                    ${priorityTag}${minimumTag}
                    <span class="unfilled-missing">short by ${u.missing} crew</span>
                    ${breakdownHtml}
                `;
                unfilledItems.append(li);
            });
        } else {
            unfilledList.style.display = "none";
            unfilledItems.replaceChildren();
        }
    }
}

// ---- Summary cards ----
function renderSummaryCards(sumData) {
    const cards = document.getElementById("summaryCards");
    if (!cards) return;
    cards.style.display = "grid";

    // Coverage %
    const covValue = document.getElementById("covValue");
    const covSub = document.getElementById("covSub");
    if (covValue) {
        covValue.textContent = `${sumData.coverage_pct}%`;
        covSub.textContent = `${sumData.total_assigned} / ${sumData.total_required} slot`;
        const card = document.querySelector(".summary-card-coverage");
        if (card) {
            card.className = "summary-card summary-card-coverage";
            if (sumData.coverage_pct >= 90) card.classList.add("status-ok");
            else if (sumData.coverage_pct >= 70) card.classList.add("status-warn");
            else card.classList.add("status-red");
        }
    }

    // Shortages
    const shortValue = document.getElementById("shortValue");
    const shortSub = document.getElementById("shortSub");
    if (shortValue) {
        shortValue.textContent = sumData.total_missing;
        shortSub.textContent = `${sumData.total_missing} slot na kulang`;
    }

    // Average hours
    const avgValue = document.getElementById("avgValue");
    const avgSub = document.getElementById("avgSub");
    if (avgValue) {
        avgValue.textContent = `${sumData.average_hours} h`;
        avgSub.textContent = `Bawat crew`;
    }

    // Hours spread
    const spreadValue = document.getElementById("spreadValue");
    const spreadSub = document.getElementById("spreadSub");
    if (spreadValue) {
        spreadValue.textContent = `${sumData.hours_spread} h`;
        spreadSub.textContent = `Max − min`;
    }

    // Overtime
    const otValue = document.getElementById("otValue");
    const otSub = document.getElementById("otSub");
    if (otValue) {
        otValue.textContent = sumData.overtime_count;
        otSub.textContent = `Naka-exceed sa max`;
    }
}

// ---- Build summary metrics locally (avoid double generation) ----
function buildSummaryFromData(data) {
    let totalRequired = 0, totalAssigned = 0, totalMissing = 0;
    const employeeHours = {};
    const byDay = {};
    const byShift = {};
    const byStation = {};
    const byReason = {};
    const unfilledItems = [];

    for (const day of data) {
        const dayKey = String(day.date);
        const dayEntry = { total: 0, by_shift: {}, by_station: {} };
        byDay[dayKey] = dayEntry;

        for (const slot of (day.schedule || [])) {
            const needed = slot.needed || 0;
            const assigned = (slot.assigned || []).length;
            totalRequired += needed;
            totalAssigned += assigned;
            if (assigned < needed) totalMissing += (needed - assigned);

            // Per-employee hours
            const stationId = slot.station_id;
            for (const emp of (slot.assigned || [])) {
                const eid = emp.id;
                // Approximate 8 hours per shift (start-end diff)
                const [startTime] = (slot.time || "08:00 - 16:00").split(" - ");
                const [sh, sm] = startTime.split(":").map(Number);
                const [eh, em] = (slot.time || "08:00 - 16:00").split(" - ")[1].split(":").map(Number);
                const shiftHours = (eh * 60 + em - sh * 60 - sm) / 60;
                employeeHours[eid] = (employeeHours[eid] || 0) + shiftHours;
            }
        }

        for (const u of (day.unfilled || [])) {
            dayEntry.total += u.missing || 0;
            dayEntry.by_shift[u.shift] = (dayEntry.by_shift[u.shift] || 0) + (u.missing || 0);
            dayEntry.by_station[u.station] = (dayEntry.by_station[u.station] || 0) + (u.missing || 0);

            byShift[u.shift] = (byShift[u.shift] || 0) + (u.missing || 0);
            byStation[u.station] = (byStation[u.station] || 0) + (u.missing || 0);
            if (u.breakdown) {
                for (const [rk, cnt] of Object.entries(u.breakdown || {})) {
                    if (cnt) byReason[rk] = (byReason[rk] || 0) + cnt;
                }
            }
            unfilledItems.push({ date: day.date, ...u });
        }
    }

    const coveragePct = totalRequired ? Math.round((totalAssigned / totalRequired) * 100) : 100;
    const hoursValues = Object.values(employeeHours);
    const avgHours = hoursValues.length ? Math.round((hoursValues.reduce((a, b) => a + b, 0) / hoursValues.length) * 10) / 10 : 0;
    const hoursSpread = hoursValues.length ? Math.round((Math.max(...hoursValues) - Math.min(...hoursValues)) * 10) / 10 : 0;
    const overtimeCount = hoursValues.filter(h => h > 40).length;

    return {
        total_required: totalRequired,
        total_assigned: totalAssigned,
        total_missing: totalMissing,
        coverage_pct: coveragePct,
        average_hours: avgHours,
        hours_spread: hoursSpread,
        overtime_count: overtimeCount,
        solver_status: totalMissing === 0 ? "OPTIMAL" : totalMissing < 10 ? "FEASIBLE" : "PARTIAL",
        by_day: byDay,
        by_shift: byShift,
        by_station: byStation,
        by_reason: byReason,
        unfilled_items: unfilledItems,
        employee_hours: employeeHours,
    };
}
function renderShortageTab(sumData) {
    const tbody = document.getElementById("shortageTableBody");
    if (!tbody) return;
    tbody.replaceChildren();

    const rows = [];
    for (const [dayKey, dayEntry] of Object.entries(sumData.by_day)) {
        const dayDate = new Date(`${dayKey}T00:00:00`);
        const dayName = dayDate.toLocaleDateString(undefined, { weekday: "short" });
        for (const [station, count] of Object.entries(dayEntry.by_station || {})) {
            // Find the shift(s) missing for this station on this day
            const shifts = Object.entries(dayEntry.by_shift || {});
            // Approximate: spread missing across shifts
            const shiftName = shifts.length ? shifts[0][0] : "-";
            rows.push({ day: dayName, date: dayKey, station, shift: shiftName, missing: count });
        }
    }

    if (rows.length === 0) {
        tbody.innerHTML = "<tr><td colspan='7' class='schedule-empty-cell'>Walang kulang na slot.</td></tr>";
        return;
    }

    rows.forEach(r => {
        const tr = document.createElement("tr");
        const dayLabel = r.day;
        tr.innerHTML = `
            <td>${dayLabel} · ${new Date(`${r.date}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</td>
            <td>${r.station}</td>
            <td>${r.shift}</td>
            <td>-</td>
            <td>0</td>
            <td style="font-weight:700;color:#b91c1c;">${r.missing}</td>
            <td>Kulang na available crew</td>
        `;
        tbody.appendChild(tr);
    });
}

// ---- Oras ng Crew tab ----
function renderHoursTab(sumData) {
    const tbody = document.getElementById("hoursTableBody");
    if (!tbody) return;
    tbody.replaceChildren();

    const empHours = sumData.employee_hours || {};
    const rows = Object.entries(empHours).map(([eid, hours]) => ({ eid, hours }));

    if (rows.length === 0) {
        tbody.innerHTML = "<tr><td colspan='4' class='schedule-empty-cell'>Walang crew na may oras.</td></tr>";
        return;
    }

    rows.forEach(({ eid, hours }) => {
        const maxHours = 80; // default
        const tr = document.createElement("tr");
        const statusClass = hours > maxHours ? "status-red" : hours < maxHours * 0.8 ? "status-warn" : "status-ok";
        const statusText = hours > maxHours ? "Over max" : hours < maxHours * 0.8 ? "Below min target" : "OK";
        tr.innerHTML = `
            <td>Crew #${eid}</td>
            <td>${hours} h</td>
            <td>${maxHours} h</td>
            <td><span class="status-pill ${statusClass}">${statusText}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

// ---- Tab switching ----
document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(`tab${btn.dataset.tab}`).classList.add("active");
    });
});

// ---- Show shortages only toggle ----
window.toggleShowShortages = function() {
    const list = document.getElementById("unfilledSlotsList");
    if (list) list.style.display = list.style.display === "none" ? "block" : "none";
};

// ---- Week picker: only allow Mondays ----
const dateInput = document.getElementById("gen_week_start");
if (dateInput) {
    // Disable all dates except Mondays
    dateInput.addEventListener("input", () => {
        const d = new Date(dateInput.value);
        const day = d.getDay(); // 0=Sun, 1=Mon
        if (day !== 1) {
            dateInput.value = "";
            alert("Piliin lamang ang Lunes bilang simula ng linggo.");
        }
    });
}
document.getElementById("resultTableBody").addEventListener("click", (event) => {
    const btn = event.target.closest(".crew-pick-btn");
    if (!btn || btn.disabled) return;
    const rowEl = btn.closest("tr");
    if (!rowEl) return;
    const date = rowEl.dataset.date;
    const stationId = Number(rowEl.dataset.stationId);
    const shift = rowEl.dataset.shift;
    const day = currentWeekSchedule.find(d => d.date === date);
    if (!day) return;
    const rowData = day.schedule.find(r => r.station_id === stationId && r.shift === shift);
    if (!rowData) return;
    const crewCell = rowEl.querySelector(".schedule-crew-cell");
    const coverageCell = rowEl.querySelector(".schedule-coverage-cell");
    const countEl = coverageCell ? coverageCell.querySelector(".coverage-count") : null;
    const badgeEl = coverageCell ? coverageCell.querySelector(".coverage-badge") : null;
    openCrewPickerModal(rowData, date, crewCell, coverageCell, countEl, badgeEl);
});

// Day tab filtering for draft schedule
const dayNav = document.getElementById("scheduleDayNav");
if (dayNav) {
    dayNav.addEventListener("click", (event) => {
        const btn = event.target.closest(".day-tab");
        if (!btn) return;
        const dayKey = btn.dataset.day;
        selectedDayFilter = dayKey;
        dayNav.querySelectorAll(".day-tab").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        filterScheduleByDay(dayKey);
    });
}

function filterScheduleByDay(dayKey) {
    const rows = document.querySelectorAll("#resultTableBody tr");
    const dayHeaderRows = {};
    const visibleDays = new Set();

    // First pass: determine visibility per data row
    rows.forEach(row => {
        const rowDay = row.dataset.day;
        const isHeader = row.classList.contains("schedule-day-header");
        const isShortage = row.dataset.shortage === "true";

        if (isHeader) {
            dayHeaderRows[rowDay] = row;
            return;
        }

        const matchesDay = dayKey === "all" || rowDay === dayKey;
        const matchesShortage = !showShortagesOnly || isShortage;
        const isVisible = matchesDay && matchesShortage;
        row.style.display = isVisible ? "" : "none";
        if (isVisible) visibleDays.add(rowDay);
    });

    // Second pass: show day header only if it has at least one visible data row
    Object.keys(dayHeaderRows).forEach(day => {
        dayHeaderRows[day].style.display = visibleDays.has(day) ? "" : "none";
    });
}

function clearDraftAssignments() {
    if (!currentWeekSchedule.length) return;
    if (!window.confirm("Clear all draft assignments? This resets every slot to Unassigned (0 hrs). Published schedules are not affected.")) {
        return;
    }
    currentWeekSchedule.forEach(day => {
        (day.schedule || []).forEach(row => {
            row.assigned = [];
        });
    });
    renderSchedulePreview(currentWeekSchedule);
    validateDraftSchedule();
    markDraftDirty();
}

function toggleShowShortages() {
    showShortagesOnly = !showShortagesOnly;
    const btn = document.getElementById("showShortagesToggle");
    if (btn) {
        btn.textContent = showShortagesOnly ? "Show all slots" : "Show shortages only";
        btn.classList.toggle("btn-primary", showShortagesOnly);
        btn.classList.toggle("btn-secondary", !showShortagesOnly);
    }
    // Re-apply current day filter with shortage filter
    filterScheduleByDay(selectedDayFilter);
}

// 5. ASSIGNMENT HELPERS
function assignmentsForDate(date) {
    const day = currentWeekSchedule.find(d => d.date === date);
    if (!day) return [];
    return day.schedule.flatMap(row =>
        row.assigned
            .map(employee => ({
                user_id: employee.id,
                station_id: row.station_id,
                shift_name: row.shift,
            }))
    );
}

// 6. VALIDATE DRAFT SCHEDULE (all generated days)
async function validateDraftSchedule() {
    const message = document.getElementById("publishValidationMessage");
    const publishButton = document.getElementById("publishScheduleButton");
    const details = document.getElementById("scheduleIssuesDetails");
    const sequence = ++draftValidationSequence;
    draftIsValid = false;
    currentValidationIssues = [];
    publishButton.disabled = true;
    message.classList.remove("is-valid", "is-error");
    details.style.display = "none";
    details.innerHTML = "";
    message.innerHTML = "Checking crew qualifications, availability, weekly hours, rest, and coverage...";

    try {
        let allValid = true;
        const allIssues = [];
        for (const day of currentWeekSchedule) {
            if (sequence !== draftValidationSequence) return;
            const response = await fetch(`${API_URL}/schedules/validate`, {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${token}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    schedule_date: day.date,
                    assignments: assignmentsForDate(day.date),
                }),
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(formatApiError(data.detail, "Could not validate draft."));
            }
            if (sequence !== draftValidationSequence) return;
            if (!data.valid) {
                allValid = false;
                allIssues.push(...(Array.isArray(data.errors) ? data.errors : []).map(normalizeIssue));
            }
        }

        draftIsValid = allValid;
        if (draftIsValid) {
            message.textContent = "Coverage and crew checks passed. This draft is ready to publish.";
            message.classList.add("is-valid");
            publishButton.disabled = false;
        } else {
            currentValidationIssues = allIssues;
            renderValidationBanner(currentValidationIssues, message, details);
            publishButton.disabled = true;
        }
    } catch (error) {
        if (sequence !== draftValidationSequence) return;
        message.textContent = `Draft validation failed: ${error.message}`;
        message.classList.add("is-error");
        publishButton.disabled = true;
    }
}

function normalizeIssue(item) {
    if (typeof item === "string") {
        return { type: "general", station: null, shift: null, crew: null, reason: item, message: item };
    }
    if (item && typeof item === "object") {
        return {
            type: item.type || "general",
            station: item.station ?? null,
            shift: item.shift ?? null,
            crew: item.crew ?? null,
            reason: item.reason || item.message || String(item),
            message: item.message || item.reason || String(item),
        };
    }
    return { type: "general", station: null, shift: null, crew: null, reason: String(item), message: String(item) };
}

const ISSUE_TYPE_LABELS = {
    staffing_shortage: "staffing shortage",
    not_qualified: "walang qualified na crew",
    not_available: "walang available sa oras na ito",
    rest_rule: "rest-rule conflict",
    max_hours: "over max hours",
    leave: "approved leave",
    duplicate_day: "doble na schedule ngayong araw",
    duplicate_shift: "doble na shift ngayong araw",
    unsupported_shift: "hindi supported na shift",
    general: "issue",
};

function buildValidationSummary(issues) {
    const total = issues.length;
    if (total === 0) return null;
    const grouped = {};
    issues.forEach((issue) => {
        grouped[issue.type] = (grouped[issue.type] || 0) + 1;
    });
    const parts = Object.entries(grouped)
        .map(([type, count]) => `${count} ${ISSUE_TYPE_LABELS[type] || type}`)
        .join(", ");
    return `${total} issues bago i-publish: ${parts}`;
}

function renderValidationBanner(issues, message, details) {
    const summary = buildValidationSummary(issues);
    message.classList.add("is-error");
    message.classList.remove("is-valid");
    message.innerHTML = `<strong class="issues-summary">${escapeHtml(summary)}</strong>
        <button type="button" class="issues-toggle" id="issuesToggle" aria-expanded="false">
          Tingnan ang lahat ng issues
        </button>`;
    details.style.display = "none";
    details.innerHTML = "";
}

function toggleIssuesDetails(issues, details) {
    const btn = document.getElementById("issuesToggle");
    const expanded = details.style.display !== "none";
    if (expanded) {
        details.style.display = "none";
        details.innerHTML = "";
        btn.textContent = "Tingnan ang lahat ng issues";
        btn.setAttribute("aria-expanded", "false");
    } else {
        details.innerHTML = renderIssuesDetails(issues);
        details.style.display = "";
        btn.textContent = "Ihimay ang mga issues";
        btn.setAttribute("aria-expanded", "true");
    }
}

function renderIssuesDetails(issues) {
    if (!issues.length) return "<p class='schedule-issues-empty'>Walang issues na nakita.</p>";
    const groups = {};
    issues.forEach((issue) => {
        const key = `${issue.station ?? ""}::${issue.shift ?? ""}`;
        if (!groups[key]) {
            groups[key] = { station: issue.station, shift: issue.shift, items: [] };
        }
        groups[key].items.push(issue);
    });
    let html = `<div class="schedule-issues-list"><ul>`;
    Object.values(groups).forEach((group) => {
        html += `<li class="schedule-issue-group">
            <strong>${escapeHtml(group.station || "General")}${
                group.shift ? ` — ${escapeHtml(group.shift)}` : ""
            }</strong>
            <ul>`;
        group.items.forEach((issue) => {
            const crewText = issue.crew ? ` (${escapeHtml(issue.crew)})` : "";
            html += `<li class="schedule-issue-item issue-${issue.type}" data-station="${escapeHtmlAttr(issue.station || "")}" data-shift="${escapeHtmlAttr(issue.shift || "")}">
                <span class="schedule-issue-reason">${escapeHtml(issue.reason)}</span>${crewText}
                <button type="button" class="schedule-issue-go">Puntahan</button>
            </li>`;
        });
        html += `</ul></li>`;
    });
    html += `</ul></div>`;
    return html;
}

function escapeHtmlAttr(value) {
    return String(value).replace(/"/g, "&quot;");
}

function scrollToIssue(stationName, shiftName) {
    const rows = document.querySelectorAll("#resultTableBody tr");
    let target = null;
    for (const row of rows) {
        const stationMatch = !stationName || row.dataset.station === stationName;
        const shiftMatch = !shiftName || row.dataset.shift === shiftName;
        if (stationMatch && shiftMatch) {
            target = row;
            break;
        }
    }
    if (!target) return;
    document
        .querySelectorAll("#resultTableBody tr.schedule-issue-highlight")
        .forEach((row) => row.classList.remove("schedule-issue-highlight"));
    target.classList.add("schedule-issue-highlight");
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => target.classList.remove("schedule-issue-highlight"), 1800);
}

// Delegated clicks for issue banner: toggle details and scroll to a row.
document.body.addEventListener("click", (event) => {
    const toggle = event.target.closest("#issuesToggle");
    if (toggle) {
        event.preventDefault();
        const details = document.getElementById("scheduleIssuesDetails");
        toggleIssuesDetails(currentValidationIssues, details);
        return;
    }
    const go = event.target.closest(".schedule-issue-go");
    if (go) {
        const li = go.closest(".schedule-issue-item");
        scrollToIssue(li.dataset.station || undefined, li.dataset.shift || undefined);
    }
});

// 7. EXPORT
async function exportRoster(format, label, buttonId) {
    if (currentWeekSchedule.length === 0) return;

    const exportButton = document.getElementById(buttonId);
    exportButton.disabled = true;
    try {
        for (const day of currentWeekSchedule) {
            const response = await fetch(`${API_URL}/schedules/export.${format}`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    schedule_date: day.date,
                    rows: day.schedule.map(row => ({
                        station_id: row.station_id,
                        shift_name: row.shift,
                        assigned_user_ids: row.assigned.map(employee => employee.id),
                    })),
                }),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(formatApiError(error.detail, "Could not export schedule."));
            }

            const workbook = await response.blob();
            const downloadUrl = URL.createObjectURL(workbook);
            const link = document.createElement("a");
            const filename = response.headers
                .get("Content-Disposition")
                ?.match(/filename="([^"]+)"/i)?.[1] || `smartshift-schedule-${day.date}.${format}`;
            link.href = downloadUrl;
            link.download = filename;
            document.body.append(link);
            link.click();
            link.remove();
            window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
        }
    } catch (error) {
        window.alert(`${label} export failed: ${error.message}`);
    } finally {
        exportButton.disabled = false;
    }
}

function exportSchedule() {
    return exportRoster("xlsx", "Excel", "exportScheduleButton");
}

function exportSchedulePdf() {
    return exportRoster("pdf", "PDF", "exportPdfScheduleButton");
}

function exportScheduleDocx() {
    return exportRoster("docx", "Word", "exportDocxScheduleButton");
}

function printSchedule() {
    if (currentWeekSchedule.length > 0) window.print();
}

// 8. PUBLISH SCHEDULE (all generated days)
async function publishSchedule() {
    if (currentWeekSchedule.length === 0) {
        alert("Walang schedule na gagawin. Mag-generate muna.");
        return;
    }
    if (!draftIsValid) {
        alert("Ayusin at i-validate muna ang draft bago i-publish.");
        return;
    }

    let anyAssignments = false;
    for (const day of currentWeekSchedule) {
        if (assignmentsForDate(day.date).length > 0) {
            anyAssignments = true;
            break;
        }
    }
    if (!anyAssignments) {
        alert("Walang tao na naka-assign. Hindi pwedeng i-publish.");
        return;
    }

    const publishButton = document.getElementById("publishScheduleButton");
    publishButton.disabled = true;

    // Check each day for conflicts first
    const conflicts = [];
    for (const day of currentWeekSchedule) {
        const assignmentsToSave = assignmentsForDate(day.date);
        if (assignmentsToSave.length === 0) continue;
        try {
            const response = await fetch(`${API_URL}/schedules/publish`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
                body: JSON.stringify({
                    schedule_date: day.date,
                    assignments: assignmentsToSave,
                    force: false
                })
            });
            const data = await response.json();
            if (!response.ok) {
                if (response.status === 409) {
                    conflicts.push({ date: day.date, data });
                } else {
                    alert(`❌ Error: ${formatApiError(data.detail, "Failed to publish")}`);
                    await validateDraftSchedule();
                    publishButton.disabled = currentWeekSchedule.length === 0 || !draftIsValid;
                    return;
                }
            }
        } catch (error) {
            alert(`❌ Error: ${error.message}`);
            await validateDraftSchedule();
            publishButton.disabled = currentWeekSchedule.length === 0 || !draftIsValid;
            return;
        }
    }

    if (conflicts.length > 0) {
        showPublishConflictModal(conflicts);
        publishButton.disabled = currentWeekSchedule.length === 0 || !draftIsValid;
        return;
    }

    alert("✅ Schedule published for the whole week!");
    currentWeekSchedule = [];
    currentWeekStartDate = null;
    draftIsValid = false;
    document.getElementById("generateResult").style.display = "none";
    document.getElementById("gen_week_start").disabled = false;
    fetchScheduleTracking();
}

let pendingConflicts = [];

function showPublishConflictModal(conflicts) {
    pendingConflicts = conflicts;
    const messageEl = document.getElementById("publishConflictMessage");
    const listEl = document.getElementById("publishConflictList");
    const modal = document.getElementById("publishConflictModal");

    if (messageEl) {
        messageEl.textContent = conflicts.length === 1
            ? "May published na schedule para sa petsang ito. Gusto mo bang i-overwrite?"
            : `May ${conflicts.length} petsa na may published na schedule. Gusto mo bang i-overwrite ang lahat?`;
    }

    if (listEl) {
        listEl.innerHTML = "";
        conflicts.forEach(c => {
            const item = document.createElement("div");
            item.style.cssText = "padding:8px;border-bottom:1px solid var(--border-color);font-size:13px;";
            const dateStr = new Date(c.date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
            item.innerHTML = `<strong>${dateStr}</strong> - ${c.data.conflicts?.length || 0} assignment(s) will be replaced`;
            listEl.append(item);
        });
    }

    if (modal) modal.style.display = "flex";
}

function closePublishConflictModal() {
    const modal = document.getElementById("publishConflictModal");
    if (modal) modal.style.display = "none";
    pendingConflicts = [];
}

async function confirmPublishWithConflict() {
    const publishButton = document.getElementById("publishScheduleButton");
    publishButton.disabled = true;

    try {
        for (const c of pendingConflicts) {
            const assignmentsToSave = assignmentsForDate(c.date);
            if (assignmentsToSave.length === 0) continue;
            const response = await fetch(`${API_URL}/schedules/publish`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
                body: JSON.stringify({
                    schedule_date: c.date,
                    assignments: assignmentsToSave,
                    force: true
                })
            });
            const data = await response.json();
            if (!response.ok) {
                alert(`❌ Error publishing ${c.date}: ${formatApiError(data.detail, "Failed to publish")}`);
                await validateDraftSchedule();
                publishButton.disabled = currentWeekSchedule.length === 0 || !draftIsValid;
                return;
            }
        }

        closePublishConflictModal();
        alert("✅ Schedule published for the whole week!");
        currentWeekSchedule = [];
        currentWeekStartDate = null;
        draftIsValid = false;
        document.getElementById("generateResult").style.display = "none";
        document.getElementById("gen_week_start").disabled = false;
        fetchScheduleTracking();
    } catch (error) {
        alert(`❌ Error: ${error.message}`);
        await validateDraftSchedule();
    } finally {
        publishButton.disabled = currentWeekSchedule.length === 0 || !draftIsValid;
    }
}

async function saveDraftSchedule() {
    let anyAssignments = false;
    for (const day of currentWeekSchedule) {
        if (assignmentsForDate(day.date).length > 0) {
            anyAssignments = true;
            break;
        }
    }
    if (!anyAssignments) {
        alert("Walang crew assignment na ise-save. Mag-generate muna ng schedule.");
        return;
    }

    const button = document.getElementById("saveDraftScheduleButton");
    const message = document.getElementById("publishValidationMessage");
    button.disabled = true;
    try {
        for (const day of currentWeekSchedule) {
            const assignments = assignmentsForDate(day.date);
            if (assignments.length === 0) continue;
            const response = await fetch(`${API_URL}/schedules/draft`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    schedule_date: day.date,
                    assignments,
                }),
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(formatApiError(data.detail, "Could not save draft."));
            }
        }
        message.classList.remove("is-error");
        message.classList.add("is-valid");
        message.textContent = "Draft saved for the generated week. Not visible to crew until published.";
        fetchScheduleTracking();
    } catch (error) {
        message.classList.remove("is-valid");
        message.classList.add("is-error");
        message.textContent = `Draft could not be saved: ${error.message}`;
    } finally {
        button.disabled = currentWeekSchedule.length === 0;
    }
}

// 9. SCHEDULE TRACKING
async function fetchScheduleTracking() {
    const list = document.getElementById("scheduleTrackingList");
    if (!list || !user || user.role !== "manager") return;
    try {
        const response = await fetch(`${API_URL}/schedules/manager`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        const schedules = await response.json();
        if (!response.ok) {
            throw new Error(formatApiError(schedules.detail, "Could not load schedules."));
        }
        if (!Array.isArray(schedules) || schedules.length === 0) {
            const empty = document.createElement("p");
            empty.className = "schedule-tracking-empty";
            empty.textContent = "Wala pang naka-save o published na schedule.";
            list.replaceChildren(empty);
            return;
        }

        const fragment = document.createDocumentFragment();
        schedules.forEach(schedule => {
            const card = document.createElement("article");
            card.className = "schedule-tracking-card";
            const heading = document.createElement("div");
            heading.className = "schedule-tracking-card-heading";
            const title = document.createElement("h3");
            title.textContent = new Date(`${schedule.schedule_date}T00:00:00`)
                .toLocaleDateString(undefined, {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                });
            const status = document.createElement("span");
            status.className = schedule.status === "Published"
                ? "schedule-response-badge is-acknowledged"
                : "schedule-response-badge is-draft";
            status.textContent = schedule.status;
            heading.append(title, status);
            card.append(heading);

            const summary = document.createElement("p");
            summary.className = "schedule-tracking-summary";
            summary.textContent = schedule.status === "Published"
                ? `${schedule.acknowledged_count} of ${schedule.crew_count} crew acknowledged`
                : `${schedule.crew_count} crew assigned · not visible to crew`;
            card.append(summary);

            const crewList = document.createElement("ul");
            crewList.className = "schedule-response-list";
            schedule.crew.forEach(member => {
                const item = document.createElement("li");
                const name = document.createElement("span");
                name.textContent = member.crew_name;
                const responseStatus = document.createElement("span");
                responseStatus.className = member.acknowledged
                    ? "schedule-response-text is-acknowledged"
                    : "schedule-response-text is-pending";
                responseStatus.textContent = schedule.status !== "Published"
                    ? "Draft"
                    : member.acknowledged ? "Acknowledged" : "Waiting";
                item.append(name, responseStatus);
                crewList.append(item);
            });
            card.append(crewList);
            if (schedule.status === "Draft") {
                const actions = document.createElement("div");
                actions.className = "schedule-tracking-actions";

                const resumeButton = document.createElement("button");
                resumeButton.type = "button";
                resumeButton.className = "btn-secondary";
                resumeButton.textContent = "Open draft";
                resumeButton.addEventListener("click", () => openSavedDraft(schedule.schedule_date));

                const deleteButton = document.createElement("button");
                deleteButton.type = "button";
                deleteButton.className = "btn-danger-outline";
                deleteButton.textContent = "Delete draft";
                deleteButton.addEventListener("click", () => deleteDraftSchedule(schedule.schedule_date));

                actions.append(resumeButton, deleteButton);
                card.append(actions);
            }
            fragment.append(card);
        });
        list.replaceChildren(fragment);
    } catch (error) {
        console.error("Could not load schedule tracking.", error);
        const message = document.createElement("p");
        message.className = "schedule-tracking-empty is-error";
        message.textContent = `Hindi ma-load ang schedule tracking: ${error.message}`;
        list.replaceChildren(message);
    }
}

async function deleteDraftSchedule(scheduleDate) {
    const formattedDate = new Date(`${scheduleDate}T00:00:00`).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
    });
    if (!window.confirm(`Delete this draft schedule for ${formattedDate}?`)) {
        return;
    }

    try {
        const response = await fetch(
            `${API_URL}/schedules/draft?schedule_date=${encodeURIComponent(scheduleDate)}`,
            {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            },
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(formatApiError(data.detail, "Could not delete draft schedule."));
        }
        window.alert(data.message || "Draft schedule deleted.");
        fetchScheduleTracking();
    } catch (error) {
        window.alert(`Hindi natanggal ang draft: ${error.message}`);
    }
}

async function openSavedDraft(scheduleDate) {
    try {
        // Compute Monday purely from ISO date string (YYYY-MM-DD) to avoid timezone issues
        const [y, m, d] = scheduleDate.split("-").map(Number);
        const dow = new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0=Sun..6=Sat in UTC = same as local for date-only
        const mondayOffset = dow === 0 ? -6 : 1 - dow;
        const monday = new Date(Date.UTC(y, m - 1, d + mondayOffset));
        const weekStart = formatDateInput(monday);

        // Regenerate the full week so the other days have data.
        const weekRes = await fetch(
            `${API_URL}/schedules/generate-full-week?schedule_date=${weekStart}`,
            {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
            },
        );
        const weekData = await weekRes.json();
        if (!weekRes.ok) {
            throw new Error(formatApiError(weekData.detail, "Could not open saved draft."));
        }

        // Fetch the actual saved draft for this specific date so the
        // previously-saved assignments are preserved exactly.
        const draftRes = await fetch(
            `${API_URL}/schedules/draft?schedule_date=${encodeURIComponent(scheduleDate)}`,
            { headers: { Authorization: `Bearer ${token}` } },
        );
        const draftData = await draftRes.json();
        if (draftRes.ok && draftData.schedule) {
            const offset = Math.floor((new Date(`${scheduleDate}T00:00:00`) - monday) / 86400000);
            if (weekData[offset]) {
                weekData[offset] = { date: scheduleDate, schedule: draftData.schedule };
            }
        }

        const offset = Math.floor((new Date(`${scheduleDate}T00:00:00`) - monday) / 86400000);
        document.getElementById("gen_week_start").value = weekStart;
        document.getElementById("gen_week_start").disabled = true;
        document.getElementById("clearDraftAssignmentsButton").disabled = false;
        currentWeekSchedule = weekData;
        currentWeekStartDate = weekStart;
        document.getElementById("generateResult").style.display = "block";
        renderSchedulePreview(weekData);
        await fetchCrewPeriodHours();
        await validateDraftSchedule();
        document.getElementById("generateResult").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
        window.alert(`Hindi mabuksan ang saved draft: ${error.message}`);
    }
}

// 10. FETCH MANAGER STATS
async function fetchManagerStats() {
    if (!user || user.role !== "manager") return;
    try {
        const response = await fetch(`${API_URL}/stats/manager`, { headers: { "Authorization": `Bearer ${token}` }});
        if (response.ok) {
            const stats = await response.json();
            if (document.getElementById("teamMembersCount")) document.getElementById("teamMembersCount").textContent = stats.team_members;
            if (document.getElementById("todaysStaffCount")) document.getElementById("todaysStaffCount").textContent = stats.todays_staff;
            if (document.getElementById("coveragePercent")) document.getElementById("coveragePercent").textContent = stats.coverage;
            if (document.getElementById("conflictsCount")) document.getElementById("conflictsCount").textContent = stats.conflicts;
        }
    } catch (error) { console.error(error); }
}

async function fetchAssignedBranch() {
    const branchName = document.getElementById("assignedBranchName");
    const branchStatus = document.getElementById("assignedBranchStatus");
    if (!branchName || !branchStatus) return;

    try {
        const response = await fetch(`${API_URL}/branches/`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        if (response.status === 401) {
            sessionStorage.removeItem("access_token");
            sessionStorage.removeItem("user");
            window.location.replace("index.html?session=expired");
            return;
        }

        const data = await response.json();
        if (!response.ok) {
            throw new Error(formatApiError(data.detail, "Could not load assigned branch."));
        }

        const branch = data[0];
        if (!branch) {
            branchName.textContent = "No branch assigned";
            branchStatus.textContent = "Contact your Head to get a branch assignment.";
            return;
        }
        branchName.textContent = branch.name;
        branchStatus.textContent = `Operating hours: ${branch.opening_time.slice(0, 5)}–${branch.closing_time.slice(0, 5)}`;
    } catch (error) {
        branchName.textContent = "Branch unavailable";
        branchStatus.textContent = error.message;
    }
}

// 11. FETCH STATION ROSTER (Skills Directory)
function updateStationRosterBadge(count) {
    const badge = document.getElementById("stationRosterCountBadge");
    if (badge) badge.textContent = `${count} station${count === 1 ? "" : "s"}`;
}

function initStationRosterToggle() {
    const toggle = document.getElementById("stationRosterToggle");
    const wrap = document.getElementById("stationRosterBodyWrap");
    const chevron = document.getElementById("stationRosterChevron");
    if (!toggle || !wrap) return;
    toggle.addEventListener("click", () => {
        const expanded = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", String(!expanded));
        wrap.setAttribute("aria-hidden", String(expanded));
        wrap.classList.toggle("is-open", !expanded);
        if (chevron) chevron.textContent = expanded ? "▶" : "▼";
    });
}

async function fetchStationRoster() {
    const tbody = document.getElementById("station-roster-body");
    if (!tbody) return;

    try {
        const [stationsRes, crewRes] = await Promise.all([
            fetch(`${API_URL}/stations/`, { headers: { "Authorization": `Bearer ${token}` }}),
            fetch(`${API_URL}/crew/`, { headers: { "Authorization": `Bearer ${token}` }})
        ]);

        if (!stationsRes.ok || !crewRes.ok) {
            throw new Error("Hindi makuha ang station roster. Pakisubukang mag-refresh.");
        }
        const stations = await stationsRes.json();
        const crew = await crewRes.json();
        updateStationRosterBadge(Array.isArray(stations) ? stations.length : 0);

        if (stations.length === 0) {
            tbody.innerHTML = "<tr><td colspan='3' style='padding: 15px; text-align: center;'>Wala pang stations na naka-setup.</td></tr>";
            return;
        }

        tbody.innerHTML = "";

        stations.forEach(station => {
            const qualifiedCrew = crew.filter(c => {
                if (!c.qualified_stations) return false;
                const stationIds = c.qualified_stations.split(',').map(s => s.trim());
                return stationIds.includes(String(station.id));
            });

            let crewCellHtml;
            if (qualifiedCrew.length > 0) {
                const names = qualifiedCrew.map(c => `<li>${escapeHtml(c.full_name)}</li>`).join("");
                crewCellHtml = `
                    <div class="station-crew-compact">
                        <button type="button" class="station-crew-pill" aria-expanded="false">
                            ${qualifiedCrew.length} qualified crew <span aria-hidden="true">▾</span>
                        </button>
                        <ul class="station-crew-list">${names}</ul>
                    </div>`;
            } else {
                crewCellHtml = `<span class="station-crew-none">Wala pang naka-assign</span>`;
            }

            tbody.innerHTML += `
                <tr class="station-roster-row">
                    <td class="station-roster-cell"><strong>${escapeHtml(station.name)}</strong></td>
                    <td class="station-roster-cell station-roster-crew-cell">${crewCellHtml}</td>
                    <td class="station-roster-cell station-roster-actions">
                        <button type="button" class="btn-secondary" onclick="editStation(${station.id})">Edit</button>
                        <button type="button" class="btn-secondary" onclick="removeStation(${station.id})">Remove</button>
                    </td>
                </tr>
            `;
        });

    } catch (error) {
        updateStationRosterBadge(0);
        tbody.innerHTML = `<tr><td colspan="3" style="color:red; padding:15px;">❌ Error: ${escapeHtml(error.message)}</td></tr>`;
    }
}

document.getElementById("station-roster-body")?.addEventListener("click", (event) => {
    const pill = event.target.closest(".station-crew-pill");
    if (!pill) return;
    const wrap = pill.closest(".station-crew-compact");
    const expanded = pill.getAttribute("aria-expanded") === "true";
    pill.setAttribute("aria-expanded", String(!expanded));
    wrap?.classList.toggle("is-open", !expanded);
});

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    })[character]);
}

function formatApiError(detail, fallback) {
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
        const messages = detail.map(item => {
            if (typeof item === "string") return item;
            if (!item || typeof item !== "object") return "";
            const location = Array.isArray(item.loc)
                ? item.loc.filter(part => part !== "body").join(" > ")
                : "";
            return [location, item.msg].filter(Boolean).join(": ");
        }).filter(Boolean);
        if (messages.length) return messages.join("; ");
    }
    if (detail && typeof detail === "object") {
        if (typeof detail.message === "string") return detail.message;
        if (typeof detail.detail === "string") return detail.detail;
    }
    return fallback;
}

function editStation(stationId) {
    window.location.href = `stations.html?edit=${stationId}`;
}

async function removeStation(stationId) {
    if (!window.confirm("Alisin ang station na ito? Hindi ito matatanggal kung ginagamit sa published schedule.")) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/stations/${stationId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!response.ok) {
            const result = await response.json();
            throw new Error(formatApiError(result.detail, "Hindi natanggal ang station."));
        }
        await fetchStationRoster();
    } catch (error) {
        window.alert(`Hindi natanggal ang station: ${error.message}`);
    }
}

// 12. LOGOUT
function logout() {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    window.location.href = "index.html";
}

// 13. LOCAL DATE & TIME (Asia/Manila / browser local)
function getLocalDateISO() {
    try {
        return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Manila" });
    } catch (error) {
        const d = new Date();
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    }
}

function formatClockDateTime() {
    try {
        return new Date().toLocaleString("en-PH", {
            timeZone: "Asia/Manila",
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
        });
    } catch (error) {
        return new Date().toLocaleString();
    }
}

function initClock() {
    const el = document.getElementById("currentDateTime");
    if (!el) return;
    function tick() {
        el.textContent = formatClockDateTime();
    }
    tick();
    setInterval(tick, 1000);
}

// 14. CREW OVERVIEW: next/today shift + 15-day pay-period hours (40h min / 80h max)
async function fetchCrewOverview() {
    if (!user || user.role !== "employee") return;
    const dateEl = document.getElementById("crewNextShiftDate");
    const stationEl = document.getElementById("crewNextShiftStation");
    const timeEl = document.getElementById("crewNextShiftTime");
    const hoursEl = document.getElementById("crewPeriodHours");
    const statusEl = document.getElementById("crewPeriodStatus");
    const rangeEl = document.getElementById("crewPeriodRange");
    if (!dateEl && !hoursEl) return;

    const minHours = 40;
    const maxHours = 80;

    const scheduleDate = getLocalDateISO();
    try {
        const response = await fetch(
            `${API_URL}/schedules/my/overview?schedule_date=${encodeURIComponent(scheduleDate)}`,
            { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!response.ok) throw new Error("Could not load crew overview.");
        const data = await response.json();

        const worked = Number(data.worked_hours || 0);
        const effMin = Number(data.min_hours ?? minHours);
        const effMax = Number(data.max_hours ?? maxHours);

        if (rangeEl) rangeEl.textContent = data.period_label || "";
        if (hoursEl) hoursEl.textContent = `${worked.toFixed(1)} / ${effMax} hrs`;

        let statusText = "";
        if (worked >= effMax) {
            statusText = `Max hours reached (${effMax}h)`;
        } else if (worked >= effMin) {
            statusText = "On track \u2705";
        } else {
            statusText = `Below minimum (${effMin}h min)`;
        }
        if (statusEl) statusEl.textContent = statusText;

        const shift = data.today_shift || data.next_shift;
        if (dateEl) {
            dateEl.textContent = shift
                ? new Date(`${shift.schedule_date}T00:00:00`).toLocaleDateString(
                      undefined,
                      { weekday: "long", month: "long", day: "numeric" },
                  )
                : "No upcoming shift";
        }
        if (stationEl) {
            stationEl.textContent = shift && shift.station
                ? `Station: ${shift.station}`
                : "No upcoming shift";
        }
        if (timeEl) {
            timeEl.textContent = shift && shift.start_time && shift.end_time
                ? `${shift.start_time} – ${shift.end_time}`
                : "";
        }
    } catch (error) {
        console.error("Could not load crew overview.", error);
        if (dateEl) dateEl.textContent = "--";
        if (stationEl) stationEl.textContent = "No upcoming shift";
        if (timeEl) timeEl.textContent = "";
        if (hoursEl) hoursEl.textContent = `0 / ${maxHours} hrs`;
        if (statusEl) statusEl.textContent = "";
        if (rangeEl) rangeEl.textContent = "";
    }
}

// 15. FETCH CREW 15-DAY PERIOD HOURS (for Choose crew modal)
async function fetchCrewPeriodHours() {
    if (!user || user.role !== "manager") return;
    try {
        const response = await fetch(`${API_URL}/crew/hours-summary`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Could not load crew hours summary.");
        const data = await response.json();
        crewPeriodHoursById = {};
        (data.crew || []).forEach(member => {
            if (member.id != null) crewPeriodHoursById[member.id] = Number(member.worked_hours || 0);
        });
    } catch (error) {
        console.error("Could not load crew period hours.", error);
        crewPeriodHoursById = {};
    }
}

// 16. FETCH CREW ASSIGNED SHIFTS (published shifts in active 15-day period, per crew)
async function fetchCrewAssignedShifts() {
    if (!user || user.role !== "manager") return;
    try {
        const response = await fetch(`${API_URL}/crew/assigned-shifts`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Could not load crew assigned shifts.");
        const data = await response.json();
        crewAssignedShiftsById = data.shifts_by_user || {};
    } catch (error) {
        console.error("Could not load crew assigned shifts.", error);
        crewAssignedShiftsById = {};
    }
}

// 17. HOLIDAYS & PRE-HOLIDAY MIRROR
let holidaysData = [];
let preHolidayMirrorEnabled = false;

async function fetchHolidays() {
    if (!user || user.role !== "manager") return;
    try {
        const response = await fetch(`${API_URL}/holidays`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Could not load holidays.");
        holidaysData = await response.json();
        renderHolidays();
    } catch (error) {
        console.error("Could not load holidays.", error);
        holidaysData = [];
        renderHolidays();
    }
}

function renderHolidays() {
    const list = document.getElementById("holidayList");
    if (!list) return;
    if (holidaysData.length === 0) {
        list.innerHTML = '<p class="holiday-list-empty">No holidays configured.</p>';
        return;
    }
    list.innerHTML = holidaysData.map(h => {
        const dateLabel = new Date(`${h.holiday_date}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
        return `
            <div class="holiday-item">
                <div class="holiday-item-info">
                    <div class="holiday-item-date">${dateLabel} · ${h.name}</div>
                    <div class="holiday-item-type">${h.holiday_type}</div>
                </div>
                <div class="holiday-item-actions">
                    <button type="button" class="btn-icon btn-icon-delete" title="Delete holiday" onclick="deleteHoliday(${h.id})">&times;</button>
                </div>
            </div>
        `;
    }).join("");
}

async function fetchPreHolidayMirror() {
    if (!user || user.role !== "manager") return;
    try {
        const response = await fetch(`${API_URL}/settings/pre-holiday-mirror`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Could not load pre-holiday mirror setting.");
        const data = await response.json();
        preHolidayMirrorEnabled = data.value === "ON";
        updateMirrorToggleUI();
    } catch (error) {
        console.error("Could not load pre-holiday mirror setting.", error);
    }
}

function updateMirrorToggleUI() {
    const toggle = document.getElementById("preHolidayMirrorToggle");
    const status = document.getElementById("preHolidayMirrorStatus");
    if (!toggle || !status) return;
    if (preHolidayMirrorEnabled) {
        toggle.setAttribute("data-on", "true");
        toggle.setAttribute("aria-checked", "true");
        status.textContent = "ON";
    } else {
        toggle.removeAttribute("data-on");
        toggle.setAttribute("aria-checked", "false");
        status.textContent = "OFF";
    }
}

async function togglePreHolidayMirror() {
    if (!user || user.role !== "manager") return;
    const nextValue = preHolidayMirrorEnabled ? "OFF" : "ON";
    try {
        const response = await fetch(`${API_URL}/settings/pre-holiday-mirror`, {
            method: "PUT",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ value: nextValue }),
        });
        if (!response.ok) throw new Error("Could not update pre-holiday mirror setting.");
        const data = await response.json();
        preHolidayMirrorEnabled = data.value === "ON";
        updateMirrorToggleUI();
    } catch (error) {
        window.alert(`Hindi ma-update ang pre-holiday mirror: ${error.message}`);
    }
}

function openAddHolidayModal() {
    const modal = document.getElementById("addHolidayModal");
    if (modal) modal.style.display = "flex";
    const dateInput = document.getElementById("newHolidayDate");
    if (dateInput) {
        dateInput.value = getLocalDateISO();
    }
}

function closeAddHolidayModal() {
    const modal = document.getElementById("addHolidayModal");
    if (modal) modal.style.display = "none";
    const form = document.getElementById("addHolidayForm");
    if (form) form.reset();
}

async function addHoliday(event) {
    event.preventDefault();
    if (!user || user.role !== "manager") return;
    const dateInput = document.getElementById("newHolidayDate");
    const nameInput = document.getElementById("newHolidayName");
    const typeInput = document.getElementById("newHolidayType");
    const payload = {
        holiday_date: dateInput.value,
        name: nameInput.value.trim(),
        holiday_type: typeInput.value,
    };
    try {
        const response = await fetch(`${API_URL}/holidays`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const result = await response.json();
            throw new Error(result.detail || "Could not add holiday.");
        }
        closeAddHolidayModal();
        await fetchHolidays();
    } catch (error) {
        window.alert(`Hindi ma-add ang holiday: ${error.message}`);
    }
}

async function deleteHoliday(holidayId) {
    if (!user || user.role !== "manager") return;
    if (!window.confirm("Delete this holiday?")) return;
    try {
        const response = await fetch(`${API_URL}/holidays/${holidayId}`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("Could not delete holiday.");
        await fetchHolidays();
    } catch (error) {
        window.alert(`Hindi natanggal ang holiday: ${error.message}`);
    }
}

// Get holiday info for a given date
function getHolidayForDate(targetDateStr) {
    return holidaysData.find(h => h.holiday_date === targetDateStr) || null;
}

// 18. INIT
if (user) {
    initClock();
}
if (user && user.role === "manager") {
    initStationRosterToggle();
    fetchAssignedBranch();
    fetchManagerStats();
    fetchStationRoster();
    fetchScheduleTracking();
    fetchCrewPeriodHours();
    fetchCrewAssignedShifts();
    fetchHolidays();
    fetchPreHolidayMirror();
}
if (user && user.role === "employee") {
    fetchCrewOverview();
}

// Holiday mirror toggle event listeners
const mirrorToggle = document.getElementById("preHolidayMirrorToggle");
if (mirrorToggle) {
    mirrorToggle.addEventListener("click", togglePreHolidayMirror);
    mirrorToggle.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            togglePreHolidayMirror();
        }
    });
}

// Add holiday form submit
const addHolidayForm = document.getElementById("addHolidayForm");
if (addHolidayForm) {
    addHolidayForm.addEventListener("submit", addHoliday);
}

// Close add holiday modal when clicking outside
const addHolidayModal = document.getElementById("addHolidayModal");
if (addHolidayModal) {
    addHolidayModal.addEventListener("click", (e) => {
        if (e.target === addHolidayModal) closeAddHolidayModal();
    });
}
