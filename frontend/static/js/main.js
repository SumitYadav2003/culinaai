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
   FAVOURITE FILTER REFRESH CLEANUP - FINAL VERSION
   Purpose:
   - Keep filters after the user clicks "Apply Filters".
   - Clear filters when the user refreshes a filtered favourites page.
   - This avoids keeping old query parameters forever.
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

    /*
        When the user submits the filter form, save a temporary marker.
        The next page load is allowed to keep the filters.
    */
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

    /*
        First load after pressing Apply Filters:
        - Keep the filters.
        - Remove the marker immediately.
        - If the user refreshes after this, the marker will be gone.
    */
    if (filterWasJustSubmitted) {
        sessionStorage.removeItem("culinaFavouriteFilterSubmitted");
        return;
    }

    /*
        Refresh or direct reload of a filtered URL:
        - Clear query parameters.
        - Return to the clean favourites page.
    */
    window.location.replace(window.location.pathname);
});