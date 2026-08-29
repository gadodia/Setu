const form = document.querySelector("#login-form");
const password = document.querySelector("#password");
const submit = document.querySelector("#login-submit");
const error = document.querySelector("#login-error");
const toggle = document.querySelector("#password-toggle");

toggle.addEventListener("click", () => {
  const reveal = password.type === "password";
  password.type = reveal ? "text" : "password";
  toggle.textContent = reveal ? "Hide" : "Show";
  toggle.setAttribute("aria-label", reveal ? "Hide password" : "Show password");
  toggle.setAttribute("aria-pressed", String(reveal));
  password.focus();
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  error.hidden = true;
  submit.disabled = true;
  submit.textContent = "Checking…";

  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Accept": "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ password: password.value })
    });
    if (!response.ok) {
      let message = response.status === 429
        ? "Too many attempts. Wait one minute and try again."
        : "That password is not correct.";
      try { message = (await response.json()).detail || message; } catch (_ignored) { /* use safe message */ }
      throw new Error(message);
    }
    window.location.replace("/");
  } catch (loginError) {
    error.textContent = loginError.message === "Failed to fetch"
      ? "Setu could not reach the local server."
      : loginError.message;
    error.hidden = false;
    password.select();
  } finally {
    submit.disabled = false;
    submit.textContent = "Open workspace";
  }
});
