const API_URL = "http://127.0.0.1:8000";
const token = localStorage.getItem("access_token");
const userString = localStorage.getItem("user");

if (!token || !userString) window.location.href = "index.html";

let user = null;
try { user = JSON.parse(userString); } catch (e) { localStorage.clear(); window.location.href = "index.html"; }

let currentGeneratedSchedule = []; 

// 1. USER INFO & RBAC
if (user) {
    if (document.getElementById("userName")) document.getElementById("userName").textContent = user.full_name;
    if (document.getElementById("userRole")) document.getElementById("userRole").textContent = user.role.charAt(0).toUpperCase() + user.role.slice(1);
    if (document.getElementById("topBarName")) document.getElementById("topBarName").textContent = user.full_name;
}

function applyRolePermissions(role) {
    const adminOnly = document.querySelectorAll(".admin-only");
    const managerOnly = document.querySelectorAll(".manager-only");
    const employeeOnly = document.querySelectorAll(".employee-only");
    const managerActionOnly = document.querySelectorAll(".manager-action-only");

    if (role === "admin") {
        employeeOnly.forEach(el => el.style.display = "none");
        managerActionOnly.forEach(el => el.style.display = "none");
    } else if (role === "manager") {
        adminOnly.forEach(el => el.style.display = "none");
        employeeOnly.forEach(el => el.style.display = "none");
    } else if (role === "employee") {
        adminOnly.forEach(el => el.style.display = "none");
        managerOnly.forEach(el => el.style.display = "none");
        managerActionOnly.forEach(el => el.style.display = "none");
    }
}
if (user && user.role) applyRolePermissions(user.role);

// 2. MODAL CONTROLS & 7-DAY LIMIT
function openScheduleModal() { 
    document.getElementById("scheduleModal").style.display = "flex"; 
    document.getElementById("generateResult").style.display = "none";
    loadModalData(); 

    const today = new Date();
    const maxDate = new Date();
    maxDate.setDate(today.getDate() + 7);

    const formatDate = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    };

    const dateInput = document.getElementById("gen_date");
    if (dateInput) {
        dateInput.min = formatDate(today);
        dateInput.max = formatDate(maxDate);
        if (!dateInput.value) dateInput.value = formatDate(today);
    }
}

function closeScheduleModal() { document.getElementById("scheduleModal").style.display = "none"; }

// 3. LOAD DROPDOWNS SA MODAL
async function loadModalData() {
    const branchSelect = document.getElementById("gen_branch_id");
    if (branchSelect && branchSelect.options.length > 1) return;

    try {
        const bRes = await fetch(`${API_URL}/branches/`, { headers: { "Authorization": `Bearer ${token}` }});
        const branches = await bRes.json();
        
        if (branchSelect) {
            branchSelect.innerHTML = '<option value="">-- Select Branch --</option>';
            branches.forEach(b => branchSelect.innerHTML += `<option value="${b.id}">${b.name}</option>`);
        }
    } catch (error) { console.error("Error loading modal data:", error); }
}

// 4. GENERATE SCHEDULE SUBMIT
document.getElementById("generateScheduleForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    
    const branchId = document.getElementById("gen_branch_id").value;
    const date = document.getElementById("gen_date").value;
    
    // Validation
    const today = new Date(); today.setHours(0,0,0,0);
    const maxDate = new Date(today); maxDate.setDate(today.getDate() + 7);
    const selectedDate = new Date(date);
    
    if (selectedDate > maxDate || selectedDate < today) {
        alert("❌ Bawal pumili ng petsa na lampas sa 7 araw o sa nakaraan!");
        return;
    }

    const resultDiv = document.getElementById("generateResult");
    const resultBody = document.getElementById("resultTableBody");

    resultDiv.style.display = "block";
    resultBody.innerHTML = "<tr><td colspan='4' style='text-align:center; padding:20px;'>⏳ Generating schedule... Please wait.</td></tr>";

    try {
        const response = await fetch(`${API_URL}/schedules/generate-full-day?branch_id=${branchId}&schedule_date=${date}`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            resultBody.innerHTML = "";
            
            if (data.schedule.length === 0) {
                resultBody.innerHTML = "<tr><td colspan='4' style='text-align:center;'>Walang nahanap na schedule.</td></tr>";
                return;
            }

            currentGeneratedSchedule = data.schedule;

            data.schedule.forEach(row => {
                const statusColor = row.status === "Complete" ? "#27ae60" : "#e74c3c";
                const crewNames = row.assigned.length > 0 
                    ? row.assigned.map(emp => `<span style="background:#e2e8f0; padding:2px 6px; border-radius:4px; margin-right:4px; display:inline-block; margin-bottom:4px; font-size:11px;">${emp.name}</span>`).join("") 
                    : "<em style='color:#e74c3c;'>WALANG TAO</em>";
                
                resultBody.innerHTML += `
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 8px;"><strong>${row.station}</strong></td>
                        <td style="padding: 8px;">${row.shift} <br><small style="color:#666;">(${row.time})</small></td>
                        <td style="padding: 8px;">${crewNames}</td>
                        <td style="padding: 8px; color:${statusColor}; font-weight:bold;">
                            ${row.status} <br><small>(${row.assigned.length}/${row.needed})</small>
                        </td>
                    </tr>
                `;
            });
        } else {
            alert(`❌ Error: ${data.detail || "Failed to generate"}`);
        }
    } catch (error) {
        resultBody.innerHTML = `<tr><td colspan='4' style='color:red;'>❌ Error: ${error.message}</td></tr>`;
    }
});

// 5. PUBLISH SCHEDULE FUNCTION
async function publishSchedule() {
    if (currentGeneratedSchedule.length === 0) {
        alert("Walang schedule na gagawin. Mag-generate muna.");
        return;
    }

    const branchId = parseInt(document.getElementById("gen_branch_id").value);
    const date = document.getElementById("gen_date").value;

    let assignmentsToSave = [];
    
    currentGeneratedSchedule.forEach(row => {
        row.assigned.forEach(emp => {
            assignmentsToSave.push({
                user_id: emp.id,
                station_id: row.station_id,
                shift_name: row.shift
            });
        });
    });

    if (assignmentsToSave.length === 0) {
        alert("Walang tao na naka-assign. Hindi pwedeng i-publish.");
        return;
    }

    try {
        const response = await fetch(`${API_URL}/schedules/publish`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
            body: JSON.stringify({
                branch_id: branchId,
                schedule_date: date,
                assignments: assignmentsToSave
            })
        });
        const data = await response.json();

        if (response.ok) {
            alert("✅ " + data.message);
            closeScheduleModal();
            currentGeneratedSchedule = [];
        } else {
            alert(`❌ Error: ${data.detail || "Failed to publish"}`);
        }
    } catch (error) {
        alert(`❌ Error: ${error.message}`);
    }
}

// 6. FETCH MANAGER STATS
async function fetchManagerStats() {
    if (!user || (user.role !== "manager" && user.role !== "admin")) return;
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

// 7. FETCH STATION ROSTER (Skills Directory)
async function fetchStationRoster() {
    const tbody = document.getElementById("station-roster-body");
    if (!tbody) return; 

    try {
        const [stationsRes, crewRes] = await Promise.all([
            fetch(`${API_URL}/stations/`, { headers: { "Authorization": `Bearer ${token}` }}),
            fetch(`${API_URL}/crew/`, { headers: { "Authorization": `Bearer ${token}` }})
        ]);

        const stations = await stationsRes.json();
        const crew = await crewRes.json();

        if (stations.length === 0) {
            tbody.innerHTML = "<tr><td colspan='2' style='padding: 15px; text-align: center;'>Wala pang stations na naka-setup.</td></tr>";
            return;
        }

        tbody.innerHTML = ""; // Clear loading state

        stations.forEach(station => {
            const qualifiedCrew = crew.filter(c => {
                if (!c.qualified_stations) return false;
                const stationIds = c.qualified_stations.split(',').map(s => s.trim());
                return stationIds.includes(String(station.id));
            });

            const crewNames = qualifiedCrew.length > 0 
                ? qualifiedCrew.map(c => c.full_name).join(", ")
                : "<span style='color: #e74c3c; font-style: italic;'>Wala pang naka-assign</span>";

            tbody.innerHTML += `
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 15px;"><strong>${station.name}</strong></td>
                    <td style="padding: 15px; color: #334155;">${crewNames}</td>
                </tr>
            `;
        });

    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="2" style="color:red; padding:15px;">❌ Error: ${error.message}</td></tr>`;
    }
}

// 8. LOGOUT
function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    window.location.href = "index.html";
}

// INIT
if (user && (user.role === "manager" || user.role === "admin")) {
    fetchManagerStats();
    fetchStationRoster(); // <-- IDINAGDAG NATIN ITO
}