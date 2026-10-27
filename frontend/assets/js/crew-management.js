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

        // BAGO: Kung Manager, i-auto select at i-lock ang branch dropdown
        if (user.role === "manager" && branches.length > 0) {
            branchSelect.value = branches[0].id;
            branchSelect.disabled = true; // Hindi na pwedeng galawin
        }

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