/*
    CulinaAI Shopping Modal JavaScript

    Purpose:
    - Keeps shopping-list behaviour separate from template HTML.
    - Copies the shopping list ingredients to the clipboard.
    - Prints only the shopping list using the print area styled in recipe_shopping.css.
*/

document.addEventListener("DOMContentLoaded", function () {
    const copyButton = document.querySelector("[data-shopping-copy-button]");
    const printButton = document.querySelector("[data-shopping-print-button]");
    const copyFeedback = document.querySelector("[data-shopping-copy-feedback]");
    const recipeTitleElement = document.querySelector("[data-shopping-recipe-title]");

    /*
        Gets all ingredient names from the modal.

        The template will mark each ingredient using:
        data-shopping-item-name
    */
    function getShoppingItems() {
        const itemElements = document.querySelectorAll("[data-shopping-item-name]");

        return Array.from(itemElements)
            .map(function (itemElement) {
                return itemElement.textContent.trim();
            })
            .filter(function (itemName) {
                return itemName.length > 0;
            });
    }

    /*
        Shows a short success or error message below the modal buttons.
    */
    function showCopyFeedback(message, isError) {
        if (!copyFeedback) {
            return;
        }

        copyFeedback.textContent = message;
        copyFeedback.classList.remove("is-error", "is-success");

        if (isError) {
            copyFeedback.classList.add("is-error");
        } else {
            copyFeedback.classList.add("is-success");
        }

        window.setTimeout(function () {
            copyFeedback.textContent = "";
            copyFeedback.classList.remove("is-error", "is-success");
        }, 2500);
    }

    /*
        Fallback copy method for browsers where navigator.clipboard is unavailable.
    */
    function fallbackCopyText(textToCopy) {
        const temporaryTextArea = document.createElement("textarea");

        temporaryTextArea.value = textToCopy;
        temporaryTextArea.setAttribute("readonly", "");
        temporaryTextArea.style.position = "absolute";
        temporaryTextArea.style.left = "-9999px";

        document.body.appendChild(temporaryTextArea);
        temporaryTextArea.select();

        const copied = document.execCommand("copy");

        document.body.removeChild(temporaryTextArea);

        return copied;
    }

    /*
        Copy shopping list button.
    */
    if (copyButton) {
        copyButton.addEventListener("click", async function () {
            const shoppingItems = getShoppingItems();

            if (!shoppingItems.length) {
                showCopyFeedback("No shopping items found to copy.", true);
                return;
            }

            const recipeTitle = recipeTitleElement
                ? recipeTitleElement.textContent.trim()
                : "CulinaAI Recipe";

            const shoppingListText = [
                `Shopping List - ${recipeTitle}`,
                "",
                ...shoppingItems.map(function (itemName) {
                    return `- ${itemName}`;
                }),
            ].join("\n");

            try {
                if (navigator.clipboard && window.isSecureContext) {
                    await navigator.clipboard.writeText(shoppingListText);
                } else {
                    const copied = fallbackCopyText(shoppingListText);

                    if (!copied) {
                        throw new Error("Fallback copy failed");
                    }
                }

                showCopyFeedback("Shopping list copied successfully.", false);
            } catch (error) {
                showCopyFeedback("Could not copy list. Please try again.", true);
            }
        });
    }

    /*
        Print shopping list button.
        The CSS file controls print mode and only shows the shopping print area.
    */
    if (printButton) {
        printButton.addEventListener("click", function () {
            window.print();
        });
    }
});