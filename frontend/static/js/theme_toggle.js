/* =========================================================
   CulinaAI light / dark theme switch
   - base.html sets data-theme on <html> before the page paints
   - this file handles the button and remembers the choice
   ========================================================= */

(function () {
    const STORAGE_KEY = "culina-theme";
    const root = document.documentElement;
    const button = document.getElementById("culinaThemeToggle");

    function currentTheme() {
        return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
    }

    function saveTheme(theme) {
        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (error) {
            // Private browsing can block storage. The theme still works for this page.
        }
    }

    // The button shows what you will switch TO, not the current theme.
    function updateButton(theme) {
        if (!button) {
            return;
        }

        const icon = button.querySelector("i");
        const label = button.querySelector("span");
        const nextTheme = theme === "dark" ? "light" : "dark";

        icon.className = nextTheme === "dark" ? "bi bi-moon-stars" : "bi bi-sun";
        label.textContent = nextTheme === "dark" ? "Dark" : "Light";
        button.setAttribute("aria-label", `Switch to ${nextTheme} mode`);
    }

    function applyTheme(theme) {
        root.setAttribute("data-theme", theme);
        updateButton(theme);

        // Lets other scripts (for example the quality dashboard charts) redraw in the new colours.
        window.dispatchEvent(new CustomEvent("culina:themechange", { detail: { theme } }));
    }

    if (button) {
        button.addEventListener("click", function () {
            const nextTheme = currentTheme() === "dark" ? "light" : "dark";
            saveTheme(nextTheme);
            applyTheme(nextTheme);
        });
    }

    // Printed recipes and shopping lists should always use the light theme.
    let themeBeforePrint = null;

    window.addEventListener("beforeprint", function () {
        themeBeforePrint = currentTheme();
        root.setAttribute("data-theme", "light");
    });

    window.addEventListener("afterprint", function () {
        if (themeBeforePrint) {
            root.setAttribute("data-theme", themeBeforePrint);
            themeBeforePrint = null;
        }
    });

    updateButton(currentTheme());
})();
