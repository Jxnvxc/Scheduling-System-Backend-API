// ========================================
// CONFIG
// ========================================
const API_URL = "http://127.0.0.1:8000";

// ========================================
// 1. AUTH GUARD - Check kung may token
// ========================================
const token = localStorage.getItem("access_token");
const userString = localStorage.getItem("user");

// Kung walang token o user, ibalik sa login page
if (!token || !userString) {
    window.location.href = "index.html";
}

// I-parse ang user object para makuha ang role
let user = null;
try {
    user = JSON.parse(userString);
} catch (e) {
    console.error("Invalid user data in localStorage");
    localStorage.clear();
    window.location.href = "index.html";
}

// ========================================
// 2. DISPLAY USER INFO SA SIDEBAR AT TOPBAR
// ========================================
if (user) {
    const userNameEl = document.getElementById("userName");
    const userRoleEl = document.getElementById("userRole");
    const topBarNameEl = document.getElementById("topBarName");

    if (userNameEl) userNameEl.textContent = user.full_name || "User";
    if (userRoleEl) userRoleEl.textContent = user.role 
        ? user.role.charAt(0).toUpperCase() + user.role.slice(1) 
        : "User";
    if (topBarNameEl) topBarNameEl.textContent = user.full_name || "User";
}

// ========================================
// 3. APPLY ROLE PERMISSIONS (RBAC)
// ========================================
function applyRolePermissions(role) {
    const adminOnly = document.querySelectorAll(".admin-only");
    const managerOnly = document.querySelectorAll(".manager-only");
    const employeeOnly = document.querySelectorAll(".employee-only");
    const managerActionOnly = document.querySelectorAll(".manager-action-only"); // BAGO

    if (role === "admin") {
        // Admin: Kita lahat ng Admin at Manager sections
        // PERO itago ang Employee-only at Manager-actions (tulad ng Generate Schedule button)
        employeeOnly.forEach(el => el.style.display = "none");
        managerActionOnly.forEach(el => el.style.display = "none"); // <-- Ito ang magtatago sa button
        
    } else if (role === "manager") {
        // Manager: Itago ang admin-only at employee-only sections
        adminOnly.forEach(el => el.style.display = "none");
        employeeOnly.forEach(el => el.style.display = "none");
        // Kita ng Manager ang manager-action-only (Generate Schedule button)
        
    } else if (role === "employee") {
        // Employee: Itago ang admin-only, manager-only, at manager-action-only
        adminOnly.forEach(el => el.style.display = "none");
        managerOnly.forEach(el => el.style.display = "none");
        managerActionOnly.forEach(el => el.style.display = "none");
    }
}
// Tawagin ang function kapag may user at role
if (user && user.role) {
    applyRolePermissions(user.role);
}

// ========================================
// 4. FETCH MANAGER SCHEDULES (Para sa Admin)
// ========================================
async function fetchManagerSchedules() {
    const accessToken = localStorage.getItem("access_token");
    const container = document.getElementById("schedules-container");
    
    if (!container) return; 

    try {
        const response = await fetch(`${API_URL}/schedules/`, {
            method: "GET",
            headers: {
                "Authorization": `Bearer ${accessToken}`,
                "Content-Type": "application/json"
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP Error: ${response.status}`);
        }

        const schedules = await response.json();

        if (schedules.length === 0) {
            container.innerHTML = "<p>No schedules created yet.</p>";
            return;
        }

        let html = `
            <table class="schedule-table" style="width:100%; border-collapse: collapse; margin-top: 10px;">
                <thead>
                    <tr style="background-color: #f4f4f4; text-align: left;">
                        <th style="padding: 8px; border: 1px solid #ddd;">ID</th>
                        <th style="padding: 8px; border: 1px solid #ddd;">Manager</th>
                        <th style="padding: 8px; border: 1px solid #ddd;">Branch</th>
                        <th style="padding: 8px; border: 1px solid #ddd;">Date</th>
                        <th style="padding: 8px; border: 1px solid #ddd;">Shift</th>
                        <th style="padding: 8px; border: 1px solid #ddd;">Status</th>
                    </tr>
                </thead>
                <tbody>
        `;

        schedules.forEach(schedule => {
            html += `
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;">${schedule.id}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">${schedule.manager_name || "N/A"}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">${schedule.branch_name || "N/A"}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">${schedule.schedule_date || "N/A"}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">${schedule.shift_start || "N/A"} - ${schedule.shift_end || "N/A"}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">${schedule.status || "Draft"}</td>
                </tr>
            `;
        });

        html += `</tbody></table>`;
        container.innerHTML = html;

    } catch (error) {
        console.error("Error fetching schedules:", error);
        container.innerHTML = `<p class="error" style="color: red;">❌ Error loading schedules: ${error.message}</p>`;
    }
}

// Tawagin ang function na ito kapag Admin ang naka-login
if (user && user.role === "admin") {
    fetchManagerSchedules();
}

// ========================================
// 5. GENERATE SCHEDULE (Modal + Form)
// ========================================
function openScheduleModal() {
    document.getElementById("scheduleModal").style.display = "flex";
}

function closeScheduleModal() {
    document.getElementById("scheduleModal").style.display = "none";
}

const scheduleForm = document.getElementById("scheduleForm");
if (scheduleForm) {
    scheduleForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const token = localStorage.getItem("access_token");
        const payload = {
            branch_name: document.getElementById("branch_name").value,
            schedule_date: document.getElementById("schedule_date").value,
            shift_start: document.getElementById("shift_start").value,
            shift_end: document.getElementById("shift_end").value
        };

        try {
            const response = await fetch(`${API_URL}/schedules/`, {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${token}`,
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (response.ok) {
                alert("✅ Schedule created successfully!");
                closeScheduleModal();
                scheduleForm.reset();
                fetchManagerSchedules(); // I-refresh ang listahan
            } else {
                alert(`❌ Error: ${data.detail || "Failed to create schedule"}`);
            }
        } catch (error) {
            alert(`❌ Error: ${error.message}`);
        }
    });
}
// ========================================
// 8. FETCH MANAGER STATS (Team Members, etc.)
// ========================================
async function fetchManagerStats() {
    const accessToken = localStorage.getItem("access_token");
    
    // Tanging Manager at Admin lang ang kailangan nito
    if (!user || (user.role !== "manager" && user.role !== "admin")) return;

    try {
        const response = await fetch(`${API_URL}/stats/manager`, {
            method: "GET",
            headers: {
                "Authorization": `Bearer ${accessToken}`,
                "Content-Type": "application/json"
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP Error: ${response.status}`);
        }

        const stats = await response.json();

        // I-update ang mga numbers sa HTML base sa galing sa backend
        const teamEl = document.getElementById("teamMembersCount");
        const todayEl = document.getElementById("todaysStaffCount");
        const coverageEl = document.getElementById("coveragePercent");
        const conflictsEl = document.getElementById("conflictsCount");

        if (teamEl) teamEl.textContent = stats.team_members;
        if (todayEl) todayEl.textContent = stats.todays_staff;
        if (coverageEl) coverageEl.textContent = stats.coverage;
        if (conflictsEl) conflictsEl.textContent = stats.conflicts;

    } catch (error) {
        console.error("Error fetching manager stats:", error);
    }
}

// Tawagin ang function kapag nag-load ang page at Manager o Admin ang naka-login
if (user && (user.role === "manager" || user.role === "admin")) {
    fetchManagerStats();
}
// ========================================
// 9. CREW MANAGEMENT (Manager Only)
// ========================================
async function fetchCrew() {
    const container = document.getElementById("crew-list");
    if (!container) return;

    try {
        const response = await fetch(`${API_URL}/crew/`, {
            headers: { "Authorization": `Bearer ${token}` }
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const crew = await response.json();

        if (crew.length === 0) {
            container.innerHTML = "<p>No crew members yet. Add one above!</p>";
            return;
        }

        let html = `
            <table style="width:100%; border-collapse:collapse; background:white; border-radius:10px; overflow:hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
                <thead>
                    <tr style="background:#f4f4f4; text-align:left;">
                        <th style="padding:12px;">ID</th>
                        <th style="padding:12px;">Full Name</th>
                        <th style="padding:12px;">Email</th>
                        <th style="padding:12px;">Employment</th>
                        <th style="padding:12px;">Crew Type</th>
                        <th style="padding:12px;">Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;

        crew.forEach(c => {
            html += `
                <tr>
                    <td style="padding:12px; border-bottom:1px solid #eee;">${c.id}</td>
                    <td style="padding:12px; border-bottom:1px solid #eee;">${c.full_name}</td>
                    <td style="padding:12px; border-bottom:1px solid #eee;">${c.email}</td>
                    <td style="padding:12px; border-bottom:1px solid #eee;">${c.employment_type || "N/A"}</td>
                    <td style="padding:12px; border-bottom:1px solid #eee;">${c.crew_type || "N/A"}</td>
                    <td style="padding:12px; border-bottom:1px solid #eee;">
                        <button onclick="deleteCrew(${c.id})" 
                                style="background:#e74c3c; color:white; border:none; padding:6px 12px; border-radius:5px; cursor:pointer;">
                            Delete
                        </button>
                    </td>
                </tr>
            `;
        });

        html += `</tbody></table>`;
        container.innerHTML = html;

    } catch (error) {
        container.innerHTML = `<p style="color:red;">❌ Error: ${error.message}</p>`;
    }
}

// CREATE NEW CREW
const crewForm = document.getElementById("crewForm");
if (crewForm) {
    crewForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const selectedTypes = Array.from(document.querySelectorAll('.crew-type-cb:checked'))
                                 .map(cb => cb.value)
                                 .join(', ');

        const payload = {
            full_name: document.getElementById("crew_name").value,
            email: document.getElementById("crew_email").value,
            employment_type: document.getElementById("employment_type").value,
            crew_type: selectedTypes || "Unassigned"
        };

        try {
            const response = await fetch(`${API_URL}/crew/`, {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${token}`,
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (response.ok) {
                alert("✅ Crew member added successfully!");
                crewForm.reset();
                fetchCrew();
                fetchManagerStats(); // I-refresh ang Team Members count
            } else {
                alert(`❌ Error: ${data.detail || "Failed to add crew"}`);
            }
        } catch (error) {
            alert(`❌ Error: ${error.message}`);
        }
    });
}

// DELETE CREW
async function deleteCrew(id) {
    if (!confirm("Are you sure you want to delete this crew member?")) return;

    try {
        const response = await fetch(`${API_URL}/crew/${id}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });

        if (response.ok) {
            alert("✅ Crew member deleted!");
            fetchCrew();
            fetchManagerStats();
        } else {
            alert("❌ Failed to delete crew.");
        }
    } catch (error) {
        alert(`❌ Error: ${error.message}`);
    }
}

// Tawagin ang fetchCrew kapag Manager o Admin ang naka-login
if (user && (user.role === "manager" || user.role === "admin")) {
    fetchCrew();
}
// ========================================
// 10. FETCH BRANCHES AND STATIONS FOR CREW FORM
// ========================================
async function loadFormData() {
    const branchSelect = document.getElementById("branch_id_select");
    const stationsContainer = document.getElementById("stations-checkboxes");
    
    if (!branchSelect || !stationsContainer) return; // Kung wala ang form, skip

    try {
        // 1. Fetch Branches
        const branchRes = await fetch(`${API_URL}/branches/`, { headers: { "Authorization": `Bearer ${token}` }});
        const branches = await branchRes.json();
        
        branchSelect.innerHTML = '<option value="">-- Select Branch --</option>';
        branches.forEach(b => {
            branchSelect.innerHTML += `<option value="${b.id}">${b.name}</option>`;
        });

        // 2. Fetch Stations
        const stationRes = await fetch(`${API_URL}/stations/`, { headers: { "Authorization": `Bearer ${token}` }});
        const stations = await stationRes.json();
        
        stationsContainer.innerHTML = "";
        if(stations.length === 0) {
            stationsContainer.innerHTML = "<small style='color:red;'>No stations found. Please add stations first.</small>";
        }
        
        stations.forEach(s => {
            stationsContainer.innerHTML += `
                <label style="cursor: pointer; font-size: 14px;">
                    <input type="checkbox" class="station-cb" value="${s.id}"> ${s.name}
                </label>
            `;
        });

    } catch (error) {
        console.error("Error loading form data:", error);
    }
}

// I-update ang crewForm submit listener para isama ang bagong fields
// Hanapin ang crewForm.addEventListener("submit", ...) at palitan ang payload:

    const selectedStations = Array.from(document.querySelectorAll('.station-cb:checked'))
                                .map(cb => cb.value)
                                .join(',');

    const payload = {
        full_name: document.getElementById("crew_name").value,
        email: document.getElementById("crew_email").value,
        employment_type: document.getElementById("employment_type").value,
        crew_type: selectedTypes || "Unassigned",
        branch_id: document.getElementById("branch_id_select").value ? parseInt(document.getElementById("branch_id_select").value) : null,
        min_hours: parseInt(document.getElementById("min_hours").value),
        max_hours: parseInt(document.getElementById("max_hours").value),
        qualified_stations: selectedStations || null
    };


// Tawagin ang loadFormData kapag nag-load ang page
if (user && user.role === "manager") {
    loadFormData();
}
// ========================================
// 6. LOGOUT FUNCTION
// ========================================
function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    // Siguraduhing tama ang path pabalik sa login page
    window.location.href = "index.html"; 
}

// ========================================
// 7. HIDE "GENERATE SCHEDULE" BUTTON FOR ADMIN
// ========================================
document.addEventListener("DOMContentLoaded", () => {
    if (user && user.role === "admin") {
        // Hanapin lahat ng buttons na may text na "Generate Schedule"
        document.querySelectorAll("button").forEach(btn => {
            if (btn.textContent.includes("Generate Schedule")) {
                btn.style.display = "none";  // Itago
            }
        });
    }
});