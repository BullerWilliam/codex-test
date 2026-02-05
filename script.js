const button = document.getElementById("theme-toggle");
const message = document.getElementById("message");

button.addEventListener("click", () => {
  document.body.classList.toggle("dark");

  const darkModeOn = document.body.classList.contains("dark");
  button.textContent = darkModeOn ? "Switch to light mode" : "Switch to dark mode";
  message.textContent = darkModeOn
    ? "Dark mode is now enabled."
    : "Light mode is now enabled.";
});
