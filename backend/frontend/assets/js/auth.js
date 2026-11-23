// Ang URL ng backend API natin
const API_URL = window.SMARTSHIFT_API_URL;

// ========================================
// LOGIN LOGIC
// ========================================
const loginForm = document.getElementById("loginForm");

if (loginForm) {
    const accountTypeOptions = document.querySelectorAll('input[name="accountType"]');
    const staffIdGroup = document.getElementById("staffIdGroup");
    const staffIdLabel = document.getElementById("staffIdLabel");
    const staffIdInput = document.getElementById("staffId");
    const staffIdHint = document.getElementById("staffIdHint");

    function updateLoginFields() {
        const accountType = loginForm.querySelector('input[name="accountType"]:checked').value;
        const needsStaffId = accountType === "employee" || accountType === "manager";
        const idName = accountType === "manager" ? "Manager ID" : "Employee ID";

        staffIdGroup.hidden = !needsStaffId;
        staffIdInput.required = needsStaffId;
        staffIdInput.name = accountType === "manager" ? "manager_id" : "employee_number";
        staffIdInput.value = "";
        staffIdLabel.textContent = idName;
        staffIdInput.placeholder = `Enter your ${idName}`;
        staffIdHint.textContent = accountType === "manager"
            ? "Use the Manager ID assigned to your account."
            : "Use the Employee ID assigned by your manager.";
    }

    accountTypeOptions.forEach(option => option.addEventListener("change", updateLoginFields));
    updateLoginFields();

    let loginInProgress = false;
    let loginRedirecting = false;
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (loginInProgress || loginRedirecting) return;
        loginInProgress = true;

        const accountType = loginForm.querySelector('input[name="accountType"]:checked').value;
        const submitButton = loginForm.querySelector('button[type="submit"]');
        const staffId = staffIdInput.value.trim();
        const payload = {
            email: document.getElementById("email").value.trim(),
            password: document.getElementById("password").value,
            account_type: accountType
        };
        if (accountType === "employee") payload.employee_number = staffId;
        if (accountType === "manager") payload.manager_id = staffId;
        submitButton.disabled = true;
        accountTypeOptions.forEach(option => { option.disabled = true; });
        sessionStorage.removeItem("access_token");
        sessionStorage.removeItem("user");

        try {
            const response = await fetch(`${API_URL}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            
            if (response.ok) {
                const expectedRole = accountType === "employee" ? "employee" : accountType;
                if (data.user?.role !== expectedRole) {
                    throw new Error("The authenticated account type did not match the selected account.");
                }
                loginRedirecting = true;
                sessionStorage.setItem("access_token", data.access_token);
                sessionStorage.setItem("user", JSON.stringify(data.user));
                
                showMessage("✅ Login successful! Redirecting...", "success");
                
                setTimeout(() => {
                    window.location.href = data.user.role === "head"
                        ? "head-dashboard.html"
                        : "dashboard.html";
                }, 1500);
            } else {
                showMessage(`❌ ${data.detail || "Login failed"}`, "error");
            }
        } catch (error) {
            showMessage(`❌ Error: ${error.message}`, "error");
        } finally {
            loginInProgress = false;
            if (!loginRedirecting) {
                submitButton.disabled = false;
                accountTypeOptions.forEach(option => { option.disabled = false; });
            }
        }
    });
}

// ========================================
// REGISTER LOGIC
// ========================================
const registerForm = document.getElementById("registerForm");

if (registerForm) {
    const accountTypeOptions = registerForm.querySelectorAll('input[name="accountType"]');
    const staffIdGroup = document.getElementById("staffIdGroup");
    const staffIdLabel = document.getElementById("staffIdLabel");
    const staffIdInput = document.getElementById("staffId");
    const staffIdHint = document.getElementById("staffIdHint");

    function updateRegisterFields() {
        const accountType = registerForm.querySelector('input[name="accountType"]:checked').value;
        const needsStaffId = accountType === "employee" || accountType === "manager";
        const idName = accountType === "manager" ? "Manager ID" : "Employee ID";

        staffIdGroup.hidden = !needsStaffId;
        staffIdInput.required = needsStaffId;
        staffIdInput.name = accountType === "manager" ? "manager_id" : "employee_number";
        staffIdInput.value = "";
        staffIdLabel.textContent = idName;
        staffIdInput.placeholder = `Enter your ${idName}`;
        staffIdHint.textContent = accountType === "manager"
            ? "Use the Manager ID assigned to your account."
            : "Use the Employee ID assigned by your manager.";
    }

    accountTypeOptions.forEach(option => option.addEventListener("change", updateRegisterFields));
    updateRegisterFields();

    registerForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const accountType = registerForm.querySelector('input[name="accountType"]:checked').value;
        const staffId = staffIdInput.value.trim();
        const full_name = document.getElementById("full_name").value;
        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;

        const payload = {
            email,
            full_name,
            password,
            account_type: accountType,
        };
        if (accountType === "employee") payload.employee_number = staffId;
        if (accountType === "manager") payload.manager_id = staffId;

        try {
            const response = await fetch(`${API_URL}/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (response.ok) {
                showMessage("✅ Registration successful! Redirecting to login...", "success");
                setTimeout(() => {
                window.location.href = "index.html";
                }, 1500);
            } else {
                showMessage(`❌ ${data.detail || "Registration failed"}`, "error");
            }
        } catch (error) {
            showMessage(`❌ Error: ${error.message}`, "error");
        }
    });
}

// ========================================
// Helper Function para sa Messages
// ========================================
function showMessage(message, type) {
    const messageBox = document.getElementById("message");
    if (messageBox) {
        messageBox.textContent = message;
        messageBox.className = `message ${type}`;
    }
}

if (new URLSearchParams(window.location.search).get("session") === "expired") {
    showMessage("Your session expired. Please sign in again.", "error");
}