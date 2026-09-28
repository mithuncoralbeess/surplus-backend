document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("adminLoginForm");
    const emailInput = document.getElementById("user_email");
    const passwordInput = document.getElementById("user_pass");
    const togglePassBtn = document.getElementById("togglePassBtn");
    const togglePassIcon = document.getElementById("togglePassIcon");
    const submitBtn = document.getElementById("submitBtn");
    const btnText = document.getElementById("btnText");
    const spinner = document.getElementById("btnSpinner");
    const alertBanner = document.getElementById("alertBanner");
    const alertText = document.getElementById("alertText");

    // Helper function for password visibility toggle
    function setupPasswordToggle(buttonId, iconId, inputId) {
        const btn = document.getElementById(buttonId);
        const icon = document.getElementById(iconId);
        const input = document.getElementById(inputId);

        if (btn && icon && input) {
            btn.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                const isPassword = input.type === "password";
                input.type = isPassword ? "text" : "password";
                
                if (isPassword) {
                    icon.classList.remove("bi-eye");
                    icon.classList.add("bi-eye-slash");
                } else {
                    icon.classList.remove("bi-eye-slash");
                    icon.classList.add("bi-eye");
                }
                input.focus();
            });
        }
    }

    // Initialize all password toggles
    setupPasswordToggle("togglePassBtn", "togglePassIcon", "user_pass");
    setupPasswordToggle("toggleNewPassBtn", "toggleNewPassIcon", "newPassword");
    setupPasswordToggle("toggleConfirmPassBtn", "toggleConfirmPassIcon", "confirmNewPassword");

    function showAlert(message, type = "danger") {
        alertBanner.className = `alert alert-${type} d-flex align-items-center gap-2 py-2 px-3 small rounded-3`;
        alertText.textContent = message;
        alertBanner.classList.remove("d-none");
    }

    function hideAlert() {
        alertBanner.classList.add("d-none");
    }

    function setLoading(isLoading) {
        submitBtn.disabled = isLoading;
        if (isLoading) {
            spinner.classList.remove("d-none");
            btnText.textContent = "Authenticating...";
        } else {
            spinner.classList.add("d-none");
            btnText.textContent = "Sign In to Dashboard";
        }
    }

    // Login Form Submission
    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            hideAlert();

            const userEmail = emailInput.value.trim();
            const userPass = passwordInput.value;

            if (!userEmail || !userPass) {
                showAlert("Please enter your email/username and password.");
                return;
            }

            setLoading(true);

            try {
                const response = await fetch("/admin/login/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        user_email: userEmail,
                        user_pass: userPass,
                    }),
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    showAlert(data.message || "Login successful! Redirecting...", "success");
                    setTimeout(() => {
                        window.location.href = data.redirect_url || "/admin/dashboard/";
                    }, 700);
                } else {
                    showAlert(data.message || "Invalid email or password.", "danger");
                    setLoading(false);
                }
            } catch (err) {
                showAlert("Connection error. Please check server status.", "danger");
                setLoading(false);
            }
        });
    }

    // Modal Handling for Password Reset OTP
    const sendOtpBtn = document.getElementById("sendOtpBtn");
    const verifyOtpBtn = document.getElementById("verifyOtpBtn");
    const resetEmailInput = document.getElementById("resetEmail");
    const otpStep1 = document.getElementById("otpStep1");
    const otpStep2 = document.getElementById("otpStep2");
    const modalAlert = document.getElementById("modalAlert");

    function showModalAlert(msg, isSuccess = false) {
        modalAlert.textContent = msg;
        modalAlert.className = `alert alert-${isSuccess ? "success" : "danger"} py-2 px-3 small rounded-3 mb-3`;
        modalAlert.classList.remove("d-none");
    }

    if (sendOtpBtn) {
        sendOtpBtn.addEventListener("click", async () => {
            const email = resetEmailInput.value.trim();
            if (!email) {
                showModalAlert("Please enter your SuperAdmin email.");
                return;
            }

            sendOtpBtn.disabled = true;
            sendOtpBtn.textContent = "Sending OTP...";

            try {
                const res = await fetch("/admin/password-reset/", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: email }),
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    showModalAlert("OTP generated! (Logged in server console in dev mode).", true);
                    setTimeout(() => {
                        otpStep1.classList.add("d-none");
                        otpStep2.classList.remove("d-none");
                    }, 1000);
                } else {
                    showModalAlert(data.message || "Failed to send OTP.");
                }
            } catch (e) {
                showModalAlert("Failed to connect to server.");
            } finally {
                sendOtpBtn.disabled = false;
                sendOtpBtn.textContent = "Send 6-Digit OTP";
            }
        });
    }

    if (verifyOtpBtn) {
        verifyOtpBtn.addEventListener("click", async () => {
            const email = resetEmailInput.value.trim();
            const otp = document.getElementById("otpCode").value.trim();
            const newPass = document.getElementById("newPassword").value;
            const confirmPass = document.getElementById("confirmNewPassword").value;

            if (!otp || !newPass || !confirmPass) {
                showModalAlert("Please fill in all fields.");
                return;
            }
            if (newPass !== confirmPass) {
                showModalAlert("New passwords do not match.");
                return;
            }

            verifyOtpBtn.disabled = true;
            verifyOtpBtn.textContent = "Verifying...";

            try {
                const res = await fetch("/admin/verify-otp/", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        email: email,
                        otp: otp,
                        new_password: newPass,
                        confirm_password: confirmPass,
                    }),
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    showModalAlert("Password updated successfully! Redirecting to login...", true);
                    setTimeout(() => {
                        const modalEl = document.getElementById("otpResetModal");
                        const modalInstance = bootstrap.Modal.getInstance(modalEl);
                        if (modalInstance) modalInstance.hide();
                        showAlert("Password reset successfully. Please sign in.", "success");
                    }, 1200);
                } else {
                    showModalAlert(data.message || "Invalid or expired OTP.");
                }
            } catch (e) {
                showModalAlert("Failed to connect to server.");
            } finally {
                verifyOtpBtn.disabled = false;
                verifyOtpBtn.textContent = "Reset Password";
            }
        });
    }
});
