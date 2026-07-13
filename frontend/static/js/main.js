/* =========================================================
   CULINAAI MAIN JAVASCRIPT
   Purpose:
   - Auto-hide global Django messages
   - Handle favourite filter refresh cleanup
   - Handle password show/hide buttons
   ========================================================= */


/* =========================================================
   GLOBAL MESSAGE AUTO HIDE
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    const messages = document.querySelectorAll(".global-message");

    messages.forEach(function (message) {
        setTimeout(function () {
            message.classList.add("message-hide");

            setTimeout(function () {
                message.remove();
            }, 350);
        }, 2200);
    });
});


/* =========================================================
   FAVOURITE FILTER REFRESH CLEANUP
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    const favouriteRecipesPage = document.querySelector(
        "[data-clear-favourite-filters-on-refresh='true']"
    );

    if (!favouriteRecipesPage) {
        return;
    }

    const filterForm = favouriteRecipesPage.querySelector(".recipe-filter-form");
    const hasQueryString = window.location.search.length > 0;

    if (filterForm) {
        filterForm.addEventListener("submit", function () {
            sessionStorage.setItem("culinaFavouriteFilterSubmitted", "true");
        });
    }

    if (!hasQueryString) {
        sessionStorage.removeItem("culinaFavouriteFilterSubmitted");
        return;
    }

    const filterWasJustSubmitted =
        sessionStorage.getItem("culinaFavouriteFilterSubmitted") === "true";

    if (filterWasJustSubmitted) {
        sessionStorage.removeItem("culinaFavouriteFilterSubmitted");
        return;
    }

    window.location.replace(window.location.pathname);
});


/* =========================================================
   PASSWORD SHOW / HIDE TOGGLE
   Works for:
   - Login page password
   - Signup page password
   - Signup page confirm password
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    const passwordToggleButtons = document.querySelectorAll(
        "[data-culina-password-toggle]"
    );

    passwordToggleButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            const targetId = button.getAttribute("data-target-id");
            const passwordInput = document.getElementById(targetId);
            const icon = button.querySelector("i");

            if (!passwordInput) {
                return;
            }

            if (passwordInput.type === "password") {
                passwordInput.type = "text";
                button.setAttribute("aria-label", "Hide password");

                if (icon) {
                    icon.classList.remove("bi-eye");
                    icon.classList.add("bi-eye-slash");
                }
            } else {
                passwordInput.type = "password";
                button.setAttribute("aria-label", "Show password");

                if (icon) {
                    icon.classList.remove("bi-eye-slash");
                    icon.classList.add("bi-eye");
                }
            }
        });
    });
});


/* =========================================================
   LOGIN PAGE FOCUS AFTER SUCCESSFUL SIGNUP
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    const animatedLoginCard = document.querySelector(".culina-auth-card-turn-in");

    if (!animatedLoginCard) {
        return;
    }

    const emailInput = document.getElementById("id_username");

    if (emailInput) {
        setTimeout(function () {
            emailInput.focus();
        }, 700);
    }
});













/* =========================================================
   REAL SIGNUP SUCCESS TO LOGIN FLIP
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    const flipCard = document.querySelector("[data-auth-flip-card]");

    if (!flipCard) {
        return;
    }

    setTimeout(function () {
        flipCard.classList.add("is-flipped");
    }, 900);

    setTimeout(function () {
        const emailInput = document.getElementById("id_username");

        if (emailInput) {
            emailInput.focus();
        }
    }, 2300);
});