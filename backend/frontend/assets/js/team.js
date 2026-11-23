const API_URL = window.SMARTSHIFT_API_URL;
const token = sessionStorage.getItem("access_token");
const userString = sessionStorage.getItem("user");

if (!token || !userString) window.location.replace("index.html");

let user = null;
try {
    user = JSON.parse(userString);
} catch (e) {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    window.location.replace("index.html");
}

if (user && user.role !== "manager") {
    window.location.replace("dashboard.html");
}

if (user) {
    const userNameEl = document.getElementById("userName");
    const userRoleEl = document.getElementById("userRole");
    const topBarNameEl = document.getElementById("topBarName");
    if (userNameEl) userNameEl.textContent = user.full_name || "";
    if (userRoleEl) userRoleEl.textContent = user.role === "employee" ? "Crew" : "Manager";
    if (topBarNameEl) topBarNameEl.textContent = user.full_name || "";
}

async function fetchTeamDirectory() {
    const directory = document.getElementById("crewDirectory");
    if (!directory) return;

    try {
        const headers = { Authorization: `Bearer ${token}` };
        const [crewResponse, stationsResponse] = await Promise.all([
            fetch(`${API_URL}/crew/`, { headers }),
            fetch(`${API_URL}/stations/`, { headers }),
        ]);

        if (crewResponse.status === 401 || stationsResponse.status === 401) {
            sessionStorage.removeItem("access_token");
            sessionStorage.removeItem("user");
            window.location.replace("index.html?session=expired");
            return;
        }

        const [crewResult, stationsResult] = await Promise.all([
            readApiResponse(crewResponse, "Could not load branch crew."),
            readApiResponse(stationsResponse, "Could not load branch stations."),
        ]);
        const crew = crewResult.data;
        const stationNames = new Map(
            stationsResult.data.map(station => [String(station.id), station.name]),
        );

        if (crew.length === 0) {
            directory.innerHTML = '<tr><td colspan="5">No crew members yet. Add crew from Crew Management.</td></tr>';
            return;
        }

        directory.innerHTML = crew.map(member => renderCrewRow(member, stationNames)).join("");

    } catch (error) {
        directory.innerHTML = `<tr><td colspan="5">Unable to load team: ${escapeHTML(error.message)}</td></tr>`;
    }
}

async function readApiResponse(response, fallback) {
    const data = await response.json();
    if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : fallback;
        throw new Error(detail);
    }
    return { data };
}

function renderCrewRow(member, stationNames) {
    const skills = (member.crew_type || "")
        .split(",")
        .map(skill => skill.trim())
        .filter(Boolean);
    const stationIds = (member.qualified_stations || "")
        .split(",")
        .map(id => id.trim())
        .filter(Boolean);
    const stations = stationIds
        .map(id => stationNames.get(id))
        .filter(Boolean);

    return `
        <tr>
            <td>
                <strong>${escapeHTML(member.full_name)}</strong>
                <br><small>${escapeHTML(member.email)}</small>
            </td>
            <td>${escapeHTML(member.employee_number || "Not assigned")}</td>
            <td>${renderTags(skills, "No skills listed")}</td>
            <td>${escapeHTML(member.employment_type || "Not specified")}</td>
            <td>${renderTags(stations, "No stations assigned")}</td>
        </tr>
    `;
}

function renderTags(values, emptyLabel) {
    if (values.length === 0) return `<span class="team-empty-value">${emptyLabel}</span>`;
    return values.map(value => `<span class="team-tag">${escapeHTML(value)}</span>`).join(" ");
}

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[character]);
}

function logout() {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    window.location.href = "index.html";
}

fetchTeamDirectory();