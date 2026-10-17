// Ang URL ng backend API natin
const API_URL = "http://127.0.0.1:8000";

// ========================================
// LOGIN LOGIC
// ========================================
const loginForm = document.getElementById("loginForm");

if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;
        
        try {
            const response = await fetch(`${API_URL}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                // I-save ang token sa localStorage
                localStorage.setItem("access_token", data.access_token);
                localStorage.setItem("user", JSON.stringify(data.user));
                
                showMessage("✅ Login successful! Redirecting...", "success");
                
                setTimeout(() => {
                    window.location.href = "dashboard.html"; // Palitan kung may dashboard ka na
                }, 1500);
            } else {
                showMessage(`❌ ${data.detail || "Login failed"}`, "error");
            }
        } catch (error) {
            showMessage(`❌ Error: ${error.message}`, "error");
        }
    });
}

// ========================================
// REGISTER LOGIC
// ========================================
const registerForm = document.getElementById("registerForm");

if (registerForm) {
    registerForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const full_name = document.getElementById("full_name").value;
        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;
        const role = document.getElementById("role").value;
        
        try {
            const response = await fetch(`${API_URL}/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, full_name, password, role })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                showMessage("✅ Registration successful! Redirecting to login...", "success");
                setTimeout(() => {
                window.location.href = "index.html"; // Hindi dashboard.html
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