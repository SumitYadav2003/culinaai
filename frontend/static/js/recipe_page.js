/* =========================================================
   Recipe pages: small helpers
   - "View original recipe" shows the original under a changed version
   - typing your own change selects "custom"
   - buttons say what is happening while a form is sent
   ========================================================= */

(function () {
    document.querySelectorAll("[data-toggle-original]").forEach(function (button) {
        const target = document.getElementById(button.getAttribute("aria-controls"));
        if (!target) {
            return;
        }
        button.addEventListener("click", function () {
            const opening = target.hidden;
            target.hidden = !opening;
            button.setAttribute("aria-expanded", opening ? "true" : "false");
            button.textContent = opening ? "Hide original recipe" : "View original recipe";
            if (opening) {
                target.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        });
    });

    document.querySelectorAll(".rp-change-form").forEach(function (form) {
        const text = form.querySelector("[data-custom-text]");
        const radios = form.querySelectorAll("input[name='modification_type']");
        if (!text) {
            return;
        }
        // A typed change wins over a chip left selected by mistake only if no chip was picked.
        form.addEventListener("submit", function (event) {
            const picked = Array.from(radios).some(function (radio) { return radio.checked; });
            if (!picked && !text.value.trim()) {
                event.preventDefault();
                event.stopImmediatePropagation();
                text.focus();
                text.setAttribute("placeholder", "Pick a change above, or type what you want here");
            }
        }, true);
    });

    document.querySelectorAll("[data-busy-form]").forEach(function (form) {
        form.addEventListener("submit", function () {
            if (typeof form.checkValidity === "function" && !form.checkValidity()) {
                return;
            }
            const button = form.querySelector("[data-busy-text]");
            if (button) {
                window.setTimeout(function () {
                    button.disabled = true;
                    button.textContent = button.getAttribute("data-busy-text");
                }, 0);
            }
        });
    });
})();
