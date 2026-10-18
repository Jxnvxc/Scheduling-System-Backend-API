const API_URL = "http://127.0.0.1:8000";
const token = localStorage.getItem("access_token");
const userString = localStorage.getItem("user");

if (!token || !userString) {
    window.location.href = "index.html";
}

let user = null;
try { user = JSON.parse(userString); } 
catch (e) { localStorage.clear(); window.location.href = "index.html"; }

// 1. DISPLAY USER INFO
if (user) {
    if (document.getElementById("userName")) document.getElementById("userName").textContent = user.full_name || "User";
    if (document.getElementById("userRole")) document.getElementById("userRole").textContent = user.role ? user.role.charAt(0).toUpperCase() + user.role.slice(1) : "User";
    if (document.getElementById("topBarName")) document.getElementById("topBarName").textContent = user.full_name || "User";
}

// 2. APPLY ROLE PERMISSIONS
function applyRolePermissions(role) {
    const adminOnly = document.querySelectorAll(".admin-only");
    const managerOnly = document.querySelectorAll(".manager-only");
    const employeeOnly = document.querySelectorAll(".employee-only");
    const managerActionOnly = document.querySelectorAll(".manager-action-only");

    if (role === "admin") {
        // Admin: Nakikita lang ang Admin Overview at Review Schedules SA DASHBOARD.
        // Pero sa sidebar, kita niya lahat ng links para makapasok siya sa ibang pages.
        managerOnly.forEach(el => el.style.display = "none");
        employeeOnly.forEach(el => el.style.display = "none");
        managerActionOnly.forEach(el => el.style.display = "none");
        
    } else if (role === "manager") {
        // Manager: Nakikita ang Manager Overview. Tinatago ang Admin.
        adminOnly.forEach(el => el.style.display = "none");
        employeeOnly.forEach(el => el.style.display = "none");
        
    } else if (role === "employee") {
        // Employee: Nakikita lang ang Employee Overview.
        adminOnly.forEach(el => el.style.display = "none");
        managerOnly.forEach(el => el.style.display = "none");
        managerActionOnly.forEach(el => el.style.display = "none");
    }
}
if (user && user.role) applyRolePermissions(user.role);

// 3. FETCH MANAGER STATS
async function fetchManagerStats() {
    if (!user || (user.role !== "manager" && user.role !== "admin")) return;
    try {
        const response = await fetch(`${API_URL}/stats/manager`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (response.ok) {
            const stats = await response.json();
            if (document.getElementById("teamMembersCount")) document.getElementById("teamMembersCount").textContent = stats.team_members;
            if (document.getElementById("todaysStaffCount")) document.getElementById("todaysStaffCount").textContent = stats.todays_staff;
            if (document.getElementById("coveragePercent")) document.getElementById("coveragePercent").textContent = stats.coverage;
            if (document.getElementById("conflictsCount")) document.getElementById("conflictsCount").textContent = stats.conflicts;
        }
    } catch (error) { console.error(error); }
}

// 4. FETCH SCHEDULES (For Admin View)
async function fetchManagerSchedules() {
    const container = document.getElementById("schedules-container");
    if (!container) return; 
    try {
        const response = await fetch(`${API_URL}/schedules/`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
        const schedules = await response.json();

        if (schedules.length === 0) {
            container.innerHTML = "<p>No schedules created yet.</p>";
            return;
        }

        let html = `<table><thead><tr><th>ID</th><th>Manager</th><th>Branch</th><th>Date</th><th>Shift</th><th>Status</th></tr></thead><tbody>`;
        schedules.forEach(s => {
            html += `<tr>
                <td>${s.id}</td><td>${s.manager_name || "N/A"}</td><td>${s.branch_name || "N/A"}</td>
                <td>${s.schedule_date || "N/A"}</td><td>${s.shift_start || "N/A"} - ${s.shift_end || "N/A"}</td>
                <td>${s.status || "Draft"}</td>
            </tr>`;
        });
        html += `</tbody></table>`;
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<p style="color: red;">❌ Error: ${error.message}</p>`;
    }
}

// 5. SCHEDULE MODAL CONTROLS
function openScheduleModal() { document.getElementById("scheduleModal").style.display = "flex"; }
function closeScheduleModal() { document.getElementById("scheduleModal").style.display = "none"; }

const scheduleForm = document.getElementById("scheduleForm");
if (scheduleForm) {
    scheduleForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            branch_name: document.getElementById("branch_name").value,
            schedule_date: document.getElementById("schedule_date").value,
            shift_start: document.getElementById("shift_start").value,
            shift_end: document.getElementById("shift_end").value
        };

        try {
            const response = await fetch(`${API_URL}/schedules/`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (response.ok) {
                alert("✅ Schedule created successfully!");
                closeScheduleModal();
                scheduleForm.reset();
                fetchManagerSchedules();
            } else {
                alert(`❌ Error: ${data.detail || "Failed"}`);
            }
        } catch (error) { alert(`❌ Error: ${error.message}`); }
    });
}

// 6. LOGOUT
function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    window.location.href = "index.html";
}

// INIT
if (user && (user.role === "manager" || user.role === "admin")) {
    fetchManagerStats();
    fetchManagerSchedules();
}