const API_URL = "http://127.0.0.1:8000";
const token = localStorage.getItem("access_token");
const userString = localStorage.getItem("user");

if (!token || !userString) {
    window.location.href = "../index.html";
}

let user = null;
try {
    user = JSON.parse(userString);
} catch (e) {
    localStorage.clear();
    window.location.href = "../index.html";
}

if (user) {
    const userNameEl = document.getElementById("userName");
    const userRoleEl = document.getElementById("userRole");
    const topBarNameEl = document.getElementById("topBarName");
    if (userNameEl) userNameEl.textContent = user.full_name || "User";
    if (userRoleEl) userRoleEl.textContent = user.role ? user.role.charAt(0).toUpperCase() + user.role.slice(1) : "User";
    if (topBarNameEl) topBarNameEl.textContent = user.full_name || "User";
}

const CREW_POSITIONS = [
    { key: "Production crew",    icon: "🏭", color: "#3498db" },
    { key: "Service crew",       icon: "🍽️", color: "#e67e22" },
    { key: "Gel crew",           icon: "🧴", color: "#9b59b6" },
    { key: "Crew Trainer",       icon: "🎓", color: "#2ecc71" },
    { key: "Maintenance crew",   icon: "🔧", color: "#95a5a6" }
];

async function fetchGroupedCrew() {
    const container = document.getElementById("grouped-crew-container");
    if (!container) return;

    try {
        const response = await fetch(`${API_URL}/crew/`, {
            headers: { "Authorization": `Bearer ${token}` }
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const crew = await response.json();

        if (crew.length === 0) {
            container.innerHTML = "<p>No crew members yet. Add some from the Dashboard.</p>";
            return;
        }

        const groups = {};
        CREW_POSITIONS.forEach(pos => groups[pos.key] = []);
        groups["Unassigned"] = [];

        crew.forEach(c => {
            // Kinukuha ang crew_type (e.g., "Gel crew, Crew Trainer")
            const types = (c.crew_type || "Unassigned").split(",").map(t => t.trim());
            let assigned = false;
            
            types.forEach(type => {
                if (groups[type]) {
                    groups[type].push(c);
                    assigned = true;
                }
            });
            
            if (!assigned) groups["Unassigned"].push(c);
        });

        let html = "";
        CREW_POSITIONS.forEach(pos => {
            html += renderGroup(pos.icon, pos.key, pos.color, groups[pos.key]);
        });

        if (groups["Unassigned"].length > 0) {
            html += renderGroup("❓", "Unassigned", "#7f8c8d", groups["Unassigned"]);
        }

        container.innerHTML = html;

    } catch (error) {
        container.innerHTML = `<p style="color:red;">❌ Error: ${error.message}</p>`;
    }
}

function renderGroup(icon, title, color, members) {
    if (members.length === 0) {
        return `
            <div style="background:white; padding:20px; border-radius:10px; margin-bottom:20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border-left: 5px solid ${color};">
                <h3 style="margin: 0 0 10px 0; color:${color};">${icon} ${title} <span style="font-size:14px; color:#888;">(0)</span></h3>
                <p style="color:#888; font-style:italic;">No crew assigned to this position.</p>
            </div>
        `;
    }

    let membersHtml = `<div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap:12px;">`;
    members.forEach(m => {
        const employmentBadge = m.employment_type === "Full-time" 
            ? `<span style="background:#2ecc71; color:white; padding:2px 8px; border-radius:10px; font-size:11px;">Full-time</span>`
            : `<span style="background:#f39c12; color:white; padding:2px 8px; border-radius:10px; font-size:11px;">Part-time</span>`;
        
        membersHtml += `
            <div style="padding:12px; background:#f9f9f9; border-radius:8px; border:1px solid #eee;">
                <div style="font-weight:bold; margin-bottom:5px;">${m.full_name}</div>
                <div style="font-size:12px; color:#666; margin-bottom:8px;">${m.email}</div>
                ${employmentBadge}
            </div>
        `;
    });
    membersHtml += `</div>`;

    return `
        <div style="background:white; padding:20px; border-radius:10px; margin-bottom:20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border-left: 5px solid ${color};">
            <h3 style="margin: 0 0 10px 0; color:${color};">${icon} ${title} <span style="font-size:14px; color:#888;">(${members.length})</span></h3>
            ${membersHtml}
        </div>
    `;
}

function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    // Siguraduhing tama ang path pabalik sa login page
    window.location.href = "index.html"; 
}

// Patakbuhin pagka-load ng page
fetchGroupedCrew();