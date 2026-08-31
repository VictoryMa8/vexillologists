document.addEventListener("DOMContentLoaded", () => {
    const themeController = document.getElementById("theme-controller");
    if (themeController) {
        themeController.checked = document.documentElement.dataset.theme === "light";
        themeController.addEventListener("change", (event) => {
            const theme = event.target.checked ? "light" : "dark";
            document.documentElement.dataset.theme = theme;
            localStorage.setItem("theme", theme);
        });
    }

    const toastContainer = document.getElementById("toast-container");
    if (toastContainer) {
        setTimeout(() => {
            toastContainer.style.transition = "opacity 0.5s ease";
            toastContainer.style.opacity = "0";
            setTimeout(() => toastContainer.remove(), 500);
        }, 3000);
    }
});

document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-dialog]");
    if (button) document.getElementById(button.dataset.openDialog)?.showModal();
});
