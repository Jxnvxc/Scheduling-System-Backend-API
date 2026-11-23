const API = window.SMARTSHIFT_API_URL;
const token = sessionStorage.getItem("access_token");
let user = null;
try {
  user = JSON.parse(sessionStorage.getItem("user") || "null");
} catch {
  user = null;
}

if (!token || !user) window.location.href = "index.html";

function authHeaders() {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
function setMessage(text, isError = false) {
  msg.textContent = text;
  msg.style.color = isError ? "#b91c1c" : "#166534";
}

const proofInput = document.getElementById("absence_proof");
const proofPreview = document.getElementById("proofPreview");
const proofRemove = document.getElementById("proofRemove");
let selectedProofFile = null;

proofInput.addEventListener("change", async () => {
  const file = proofInput.files[0];
  selectedProofFile = file || null;
  if (!file) {
    proofPreview.style.display = "none";
    proofPreview.innerHTML = "";
    proofRemove.style.display = "none";
    return;
  }
  const dataUrl = await fileToBase64(file);
  proofPreview.innerHTML = `<img src="${dataUrl}" class="proof-preview-img" alt="Preview" />`;
  proofPreview.style.display = "block";
  proofRemove.style.display = "inline-block";
});

proofRemove.addEventListener("click", () => {
  proofInput.value = "";
  selectedProofFile = null;
  proofPreview.style.display = "none";
  proofPreview.innerHTML = "";
  proofRemove.style.display = "none";
});

function openProofModal(src) {
  let modal = document.getElementById("proofModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "proofModal";
    modal.className = "proof-modal";
    modal.innerHTML = `
      <div class="proof-modal-overlay" onclick="closeProofModal()"></div>
      <div class="proof-modal-content" onclick="event.stopPropagation()">
        <button class="proof-modal-close" onclick="closeProofModal()">&times;</button>
        <img class="proof-modal-img" src="${src}" alt="Proof" />
      </div>`;
    document.body.appendChild(modal);
  } else {
    modal.querySelector(".proof-modal-img").src = src;
  }
  modal.style.display = "flex";
}

window.closeProofModal = function closeProofModal() {
  const modal = document.getElementById("proofModal");
  if (modal) modal.style.display = "none";
};
window.openProofModal = openProofModal;

async function loadAbsences() {
  const list = document.getElementById("absence-list");
  const count = document.getElementById("absenceCount");
  const subtitle = document.getElementById("listSubtitle");
  try {
    const endpoint = user.role === "manager" ? `${API}/absences/branch` : `${API}/absences/my`;
    const res = await fetch(endpoint, { headers: authHeaders() });
    if (!res.ok) throw new Error("Failed to load absences");
    const data = await res.json();
    count.textContent = `${data.length} records`;
    subtitle.textContent = user.role === "manager" ? "Branch absence requests" : "Your absence requests";
    if (!data.length) {
      list.innerHTML = '<div class="empty-state">No absences found.</div>';
      return;
    }
    list.innerHTML = data
      .map((a) => {
        const statusColor = {
          pending: "#f59e0b",
          approved: "#16a34a",
          rejected: "#dc2626",
        }[a.status] || "#6b7280";

        const actions =
          user.role === "manager" && a.status === "pending"
            ? `<div class="absence-actions">
                 <button class="absence-btn absence-approve" onclick="approve(${a.id})">✅ Approve</button>
                 <button class="absence-btn absence-reject" onclick="reject(${a.id})">❌ Reject</button>
               </div>`
            : user.role !== "manager" && a.status === "pending"
            ? `<button class="absence-btn absence-cancel" onclick="cancel(${a.id})">Cancel</button>`
            : "";
        return `<div class="content-card">
          <strong>${a.employee_name || "Employee"}</strong> - ${a.absence_date}
          <br/>Reason: ${a.reason || ""}
          <br/><span class="absence-status" style="color:${statusColor}; font-weight:700;">Status: ${a.status}</span>
          ${a.proof_image ? `<br/><img src="${API}/${a.proof_image}" class="absence-proof" alt="Proof" onclick="openProofModal(this.src)" />` : ""}
          <div class="form-actions">${actions}</div>
        </div>`;
      })
      .join("");
  } catch (e) {
    list.innerHTML = '<div class="empty-state">Failed to load absences.</div>';
  }
}

async function approve(id) {
  if (!window.confirm("Approve this absence request?")) return;
  const btn = document.querySelector(`button[onclick="approve(${id})"]`);
  if (btn) btn.disabled = true;
  try {
    await fetch(`${API}/absences/${id}/approve`, { method: "PUT", headers: authHeaders() });
    loadAbsences();
  } catch (e) {
    alert("Failed to approve absence.");
    if (btn) btn.disabled = false;
  }
}
async function reject(id) {
  const reason = prompt("Rejection reason:");
  if (reason === null) return;
  if (!window.confirm("Reject this absence request?")) return;
  const btn = document.querySelector(`button[onclick="reject(${id})"]`);
  if (btn) btn.disabled = true;
  try {
    await fetch(`${API}/absences/${id}/reject`, {
      method: "PUT",
      headers: authHeaders(),
      body: JSON.stringify({ reason }),
    });
    loadAbsences();
  } catch (e) {
    alert("Failed to reject absence.");
    if (btn) btn.disabled = false;
  }
}
async function cancel(id) {
  await fetch(`${API}/absences/${id}`, { method: "DELETE", headers: authHeaders() });
  loadAbsences();
}

document.getElementById("absenceForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    absence_date: document.getElementById("absence_date").value,
    reason: document.getElementById("absence_reason").value,
  };
  if (selectedProofFile) {
    payload.proof_image = await fileToBase64(selectedProofFile);
  }
  const res = await fetch(`${API}/absences/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (res.ok) {
    setMessage("Absence requested.");
    e.target.reset();
    selectedProofFile = null;
    proofPreview.style.display = "none";
    proofPreview.innerHTML = "";
    proofRemove.style.display = "none";
    loadAbsences();
  } else {
    setMessage("Failed to request absence.", true);
  }
});

// Hide request section for managers
if (user.role === "manager") {
  document.getElementById("requestSection").style.display = "none";
} else {
  document.getElementById("recordsSection").style.display = "none";
}

document.getElementById("userName").textContent = user.full_name || "";
document.getElementById("topBarName").textContent = user.full_name || "";
document.getElementById("userRole").textContent = user.role === "employee" ? "Crew" : "Manager";

document.getElementById("logoutButton").addEventListener("click", () => {
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("user");
  window.location.href = "index.html";
});

loadAbsences();
