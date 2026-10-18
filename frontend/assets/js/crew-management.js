const API_URL = "http://127.0.0.1:8000";
const token = localStorage.getItem("access_token");
const user = JSON.parse(localStorage.getItem("user"));

if (!token || !user) window.location.href = "index.html";

document.getElementById("userName").textContent = user.full_name;
document.getElementById("userRole").textContent = user.role;
document.getElementById("topBarName").textContent = user.full_name;

// 1. LOAD BRANCHES & STATIONS SA FORM
async function loadFormData() {
    const branchSelect = document.getElementById("branch_id_select");
    const stationsContainer = document.getElementById("stations-checkboxes");
    
    try {
        // Branches
        const branchRes = await fetch(`${API_URL}/branches/`, { headers: { "Authorization": `Bearer ${token}` }});
        const branches = await branchRes.json();
        branchSelect.innerHTML = '<option value="">-- Select Branch --</option>';
        branches.forEach(b => branchSelect.innerHTML += `<option value="${b.id}">${b.name}</option>`);

        // Stations
        const stationRes = await fetch(`${API_URL}/stations/`, { headers: { "Authorization": `Bearer ${token}` }});
        const stations = await stationRes.json();
        stationsContainer.innerHTML = "";
        stations.forEach(s => {
            stationsContainer.innerHTML += `
                <label style="cursor: pointer; display: flex; align-items: center;">
                    <input type="checkbox" class="station-cb" value="${s.id}" style="margin-right: 5px;"> ${s.name}
                </label>
            `;
        });
    } catch (error) {
        console.error("Error loading form data:", error);
    }
}

// 2. FETCH CREW
async function fetchCrew() {
    const container = document.getElementById("crew-list");
    try {
        const response = await fetch(`${API_URL}/crew/`, { headers: { "Authorization": `Bearer ${token}` }});
        const crew = await response.json();

        if (crew.length === 0) {
            container.innerHTML = "<p>No crew members yet. Add one above!</p>";
            return;
        }

        let html = `<table>
            <thead>
                <tr>
                    <th>ID</th><th>Full Name</th><th>Email</th><th>Employment</th><th>Crew Type</th><th>Actions</th>
                </tr>
            </thead>
            <tbody>`;

        crew.forEach(c => {
            html += `
                <tr>
                    <td>${c.id}</td>
                    <td><strong>${c.full_name}</strong></td>
                    <td>${c.email}</td>
                    <td>${c.employment_type || "N/A"}</td>
                    <td>${c.crew_type || "N/A"}</td>
                    <td>
                        <button onclick="deleteCrew(${c.id})" style="background:#ef4444; color:white; border:none; padding:6px 12px; border-radius:5px; cursor:pointer;">Delete</button>
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

// 3. SUBMIT NEW CREW
document.getElementById("crewForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    
    const selectedTypes = Array.from(document.querySelectorAll('.crew-type-cb:checked')).map(cb => cb.value).join(', ');
    const selectedStations = Array.from(document.querySelectorAll('.station-cb:checked')).map(cb => cb.value).join(',');

    const payload = {
        full_name: document.getElementById("crew_name").value,
        email: document.getElementById("crew_email").value,
        employment_type: document.getElementById("employment_type").value,
        crew_type: selectedTypes || "Unassigned",
        branch_id: parseInt(document.getElementById("branch_id_select").value),
        min_hours: parseInt(document.getElementById("min_hours").value),
        max_hours: parseInt(document.getElementById("max_hours").value),
        qualified_stations: selectedStations || null
    };

    try {
        const response = await fetch(`${API_URL}/crew/`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await response.json();

        if (response.ok) {
            alert("✅ Crew member added successfully!");
            document.getElementById("crewForm").reset();
            fetchCrew();
        } else {
            alert(`❌ Error: ${data.detail || "Failed"}`);
        }
    } catch (error) {
        alert(`❌ Error: ${error.message}`);
    }
});

// 4. DELETE CREW
async function deleteCrew(id) {
    if (!confirm("Delete this crew?")) return;
    try {
        const response = await fetch(`${API_URL}/crew/${id}`, { method: "DELETE", headers: { "Authorization": `Bearer ${token}` }});
        if (response.ok) fetchCrew();
    } catch (error) { alert(error.message); }
}

function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    window.location.href = "index.html";
}

// INIT
loadFormData();
fetchCrew();