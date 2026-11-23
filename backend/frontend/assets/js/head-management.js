const API_URL = window.SMARTSHIFT_API_URL;
const token = sessionStorage.getItem("access_token");
const managerList = document.getElementById("managerList");
const pageMessage = document.getElementById("pageMessage");
const createManagerForm = document.getElementById("createManagerForm");
const createBranchForm = document.getElementById("createBranchForm");
const managerBranchSelect = document.getElementById("managerBranch");

function showPageMessage(message, type = "") {
    pageMessage.textContent = message;
    pageMessage.className = `head-message${message ? " is-visible" : ""}${type ? ` is-${type}` : ""}`;
}

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[character]);
}

async function fetchJson(url, options = {}) {
    const response = await fetch(`${API_URL}${url}`, {
        ...options,
        headers: {
            Authorization: `Bearer ${token}`,
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...options.headers
        }
    });
    const data = response.status === 204 ? null : await response.json();
    if (!response.ok) {
        const detail = data && data.detail;
        throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
    }
    return data;
}

function renderManagers(managers, branches) {
    const managerCount = document.getElementById("managerCount");
    managerCount.textContent = `${managers.length} ${managers.length === 1 ? "manager" : "managers"}`;

    if (branches.length === 0) {
        managerList.innerHTML = `
          <div class="empty-state">
            <strong>No branches are set up yet</strong>
            An authorized operator needs to create a branch before manager accounts can be assigned.
          </div>`;
        return;
    }
    if (managers.length === 0) {
        managerList.innerHTML = `
          <div class="empty-state">
            <strong>No managers yet</strong>
            Create a manager account above to get started.
          </div>`;
        return;
    }

    managerList.innerHTML = `
        <table class="manager-table">
          <thead>
            <tr>
              <th scope="col">Manager ID</th>
              <th scope="col">Manager</th>
              <th scope="col">Email</th>
              <th scope="col">Assigned branch</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            ${managers.map(manager => `
              <tr id="manager-row-${manager.id}">
                <td class="manager-id">${escapeHtml(manager.manager_id || "Not recorded")}</td>
                <td class="manager-name">${escapeHtml(manager.full_name)}</td>
                <td class="manager-email">${escapeHtml(manager.email)}</td>
                <td><span class="branch-badge">${escapeHtml(branches.find(branch => branch.id === manager.branch_id)?.name || "Not assigned")}</span></td>
                <td>
                  <button type="button" class="manager-action" data-edit-manager-id="${manager.id}">Edit settings</button>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>`;

    managerList.querySelectorAll("button[data-edit-manager-id]").forEach(button => {
        button.addEventListener("click", () => {
            const manager = managers.find(item => item.id === Number(button.dataset.editManagerId));
            if (manager) renderManagerEditor(manager, branches);
        });
    });
}

function renderManagerEditor(manager, branches) {
    document.getElementById(`manager-edit-row-${manager.id}`)?.remove();
    const row = document.getElementById(`manager-row-${manager.id}`);
    const editRow = document.createElement("tr");
    editRow.id = `manager-edit-row-${manager.id}`;
    editRow.className = "manager-edit-row";
    editRow.innerHTML = `
      <td colspan="5">
        <form class="manager-edit-form">
          <label>
            Manager ID
            <input name="manager_id" value="${escapeHtml(manager.manager_id || "")}" inputmode="numeric" pattern="[0-9]+" maxlength="32" required />
          </label>
          <label>
            Full name
            <input name="full_name" value="${escapeHtml(manager.full_name)}" maxlength="255" required />
          </label>
          <label>
            Email
            <input name="email" type="email" value="${escapeHtml(manager.email)}" required />
          </label>
          <label>
            Branch
            <select name="branch_id" required>
              ${branches.map(branch => `
                <option value="${branch.id}" ${branch.id === manager.branch_id ? "selected" : ""}>
                  ${escapeHtml(branch.name)}
                </option>
              `).join("")}
            </select>
          </label>
          <label>
            New password (optional)
            <input name="password" type="password" minlength="8" maxlength="72" autocomplete="new-password" placeholder="Leave blank to keep current password" />
          </label>
          <div class="manager-edit-actions">
            <button type="submit" class="btn-primary">Save changes</button>
            <button type="button" data-cancel-edit>Cancel</button>
          </div>
        </form>
      </td>`;
    row.insertAdjacentElement("afterend", editRow);

    const form = editRow.querySelector("form");
    form.addEventListener("submit", event => {
        event.preventDefault();
        saveManagerSettings(manager, branches, form);
    });
    editRow.querySelector("[data-cancel-edit]").addEventListener("click", () => editRow.remove());
}

async function saveManagerSettings(manager, branches, form) {
    const formData = new FormData(form);
    const branchId = Number(formData.get("branch_id"));
    const branch = branches.find(item => item.id === branchId);
    if (!branch) {
        showPageMessage("Pumili muna ng valid na branch.", "error");
        return;
    }

    if (manager.branch_id !== branchId) {
        const oldBranch = branches.find(item => item.id === manager.branch_id);
        const oldName = oldBranch ? oldBranch.name : "walang branch";
        const confirmed = window.confirm(
            `Ililipat si ${manager.full_name} mula ${oldName} papuntang ${branch.name}. ` +
            "Mananatili sa dating branch ang crew, stations, at schedules. Ituloy?"
        );
        if (!confirmed) return;
    }

    const payload = {
        manager_id: String(formData.get("manager_id")).trim(),
        full_name: String(formData.get("full_name")).trim(),
        email: String(formData.get("email")).trim(),
        branch_id: branchId
    };
    const password = String(formData.get("password"));
    if (password) payload.password = password;

    const saveButton = form.querySelector('button[type="submit"]');
    saveButton.disabled = true;
    showPageMessage("Sine-save ang manager settings...");
    try {
        const updatedManager = await fetchJson(`/head/managers/${manager.id}`, {
            method: "PUT",
            body: JSON.stringify(payload)
        });
        showPageMessage(`Na-update ang settings ni ${updatedManager.full_name}.`, "success");
        await loadAssignments();
    } catch (error) {
        showPageMessage(`Hindi na-save ang manager settings: ${error.message}`, "error");
        saveButton.disabled = false;
    }
}

async function loadBranches() {
    const branches = await fetchJson("/head/branches");
    managerBranchSelect.innerHTML = [
        '<option value="">-- Select branch --</option>',
        ...branches.map(branch =>
            `<option value="${branch.id}">${escapeHtml(branch.name)}</option>`
        )
    ].join("");
    managerBranchSelect.disabled = branches.length === 0;
    document.getElementById("createManagerButton").disabled = branches.length === 0;
    return branches;
}

async function loadAssignments() {
    managerList.innerHTML = '<div class="empty-state">Loading managers and branches...</div>';
    document.getElementById("managerCount").textContent = "Loading...";
    const [managers, branches] = await Promise.all([
        fetchJson("/head/managers"),
        loadBranches()
    ]);
    renderManagers(managers, branches);
}

createBranchForm.addEventListener("submit", async event => {
    event.preventDefault();
    const submitButton = document.getElementById("createBranchButton");
    const openingTime = document.getElementById("branchOpeningTime").value;
    const closingTime = document.getElementById("branchClosingTime").value;
    if (closingTime <= openingTime) {
        showPageMessage("Dapat mas huli ang oras ng pagsasara kaysa oras ng pagbubukas.", "error");
        return;
    }

    const payload = {
        name: document.getElementById("branchName").value.trim(),
        opening_time: openingTime,
        closing_time: closingTime,
        prep_time_minutes: Number(document.getElementById("branchPrepMinutes").value),
        closing_time_minutes: Number(document.getElementById("branchClosingMinutes").value)
    };

    submitButton.disabled = true;
    showPageMessage("Ginagawa ang branch...");
    try {
        const branch = await fetchJson("/head/branches", {
            method: "POST",
            body: JSON.stringify(payload)
        });
        createBranchForm.reset();
        document.getElementById("branchOpeningTime").value = "08:00";
        document.getElementById("branchClosingTime").value = "22:00";
        document.getElementById("branchPrepMinutes").value = "30";
        document.getElementById("branchClosingMinutes").value = "30";
        showPageMessage(`Nagawa ang branch na ${branch.name}. Maaari na itong piliin sa manager assignment.`, "success");
        await loadAssignments();
    } catch (error) {
        showPageMessage(`Hindi nagawa ang branch: ${error.message}`, "error");
    } finally {
        submitButton.disabled = false;
    }
});

createManagerForm.addEventListener("submit", async event => {
    event.preventDefault();
    const submitButton = document.getElementById("createManagerButton");
    const payload = {
        full_name: document.getElementById("managerFullName").value.trim(),
        email: document.getElementById("managerEmail").value.trim(),
        manager_id: document.getElementById("managerIdNumber").value.trim(),
        password: document.getElementById("managerPassword").value,
        branch_id: Number(managerBranchSelect.value)
    };
    if (!payload.branch_id) {
        showPageMessage("Pumili muna ng branch para sa manager.", "error");
        return;
    }

    submitButton.disabled = true;
    showPageMessage("Ginagawa ang manager account...");
    try {
        const manager = await fetchJson("/head/managers", {
            method: "POST",
            body: JSON.stringify(payload)
        });
        createManagerForm.reset();
        showPageMessage(
            `Nagawa ang manager account para kay ${manager.full_name}. ` +
            "Ibigay nang secure sa manager ang kanilang initial password.",
            "success"
        );
        await loadAssignments();
    } catch (error) {
        showPageMessage(`Hindi nagawa ang manager account: ${error.message}`, "error");
    } finally {
        submitButton.disabled = managerBranchSelect.options.length <= 1;
    }
});

async function initializeHeadPage() {
    if (!token) {
        window.location.href = "index.html";
        return;
    }
    try {
        const user = await fetchJson("/auth/me");
        if (user.role !== "head") {
            window.location.href = "dashboard.html";
            return;
        }
        document.getElementById("headName").textContent = user.full_name;
        await loadAssignments();
    } catch (error) {
        showPageMessage(`Hindi mabuksan ang Head page: ${error.message}`, "error");
        managerList.innerHTML = `
          <div class="empty-state">
            <strong>Could not load manager assignments</strong>
            Refresh the page or sign in again if your session has expired.
          </div>`;
    }
}

document.getElementById("logoutButton").addEventListener("click", () => {
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    window.location.href = "index.html";
});

initializeHeadPage();
