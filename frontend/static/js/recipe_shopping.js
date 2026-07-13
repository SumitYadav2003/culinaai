document.addEventListener("DOMContentLoaded", function () {
  const copyButton = document.querySelector("[data-shopping-copy-button]");
  const printButton = document.querySelector("[data-shopping-print-button]");
  const copyFeedback = document.querySelector("[data-shopping-copy-feedback]");
  const recipeTitleElement = document.querySelector("[data-shopping-recipe-title]");

  function getRecipeTitle() {
    if (recipeTitleElement && recipeTitleElement.textContent.trim()) {
      return recipeTitleElement.textContent.trim();
    }

    return "CulinaAI Shopping List";
  }

  function getMissingItems() {
    const items = [];

    document
      .querySelectorAll(".culina-shopping-missing-item .culina-shopping-name")
      .forEach(function (item) {
        const value = item.textContent.trim();

        if (value) {
          items.push(value);
        }
      });

    return items;
  }

  function getAvailableItems() {
    const items = [];

    document
      .querySelectorAll(".culina-shopping-available-item .culina-shopping-name")
      .forEach(function (item) {
        const value = item.textContent.trim();

        if (value) {
          items.push(value);
        }
      });

    return items;
  }

  function buildShoppingText() {
    const recipeTitle = getRecipeTitle();
    const missingItems = getMissingItems();
    const availableItems = getAvailableItems();

    const lines = [];

    lines.push("CulinaAI Shopping List");
    lines.push(recipeTitle);
    lines.push("");

    lines.push("Need to Buy:");

    if (missingItems.length > 0) {
      missingItems.forEach(function (item) {
        lines.push("- " + item);
      });
    } else {
      lines.push("All recipe ingredients are already available in your Smart Pantry.");
    }

    lines.push("");

    lines.push("Already in Pantry:");

    if (availableItems.length > 0) {
      availableItems.forEach(function (item) {
        lines.push("- " + item);
      });
    } else {
      lines.push("No pantry matches found.");
    }

    return lines.join("\n");
  }

  async function copyShoppingList() {
    const shoppingText = buildShoppingText();

    try {
      await navigator.clipboard.writeText(shoppingText);

      if (copyFeedback) {
        copyFeedback.textContent = "Shopping list copied.";
      }
    } catch (error) {
      if (copyFeedback) {
        copyFeedback.textContent = "Copy failed. Please try again.";
      }
    }

    setTimeout(function () {
      if (copyFeedback) {
        copyFeedback.textContent = "";
      }
    }, 2500);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function buildListHtml(items, emptyMessage) {
    if (!items.length) {
      return `<p>${escapeHtml(emptyMessage)}</p>`;
    }

    const listItems = items
      .map(function (item) {
        return `<li>${escapeHtml(item)}</li>`;
      })
      .join("");

    return `<ul>${listItems}</ul>`;
  }

  function printShoppingList() {
    const recipeTitle = getRecipeTitle();
    const missingItems = getMissingItems();
    const availableItems = getAvailableItems();

    const printWindow = window.open("", "_blank", "width=900,height=700");

    if (!printWindow) {
      alert("Please allow pop-ups to print the shopping list.");
      return;
    }

    const missingHtml = buildListHtml(
      missingItems,
      "All recipe ingredients are already available in your Smart Pantry."
    );

    const availableHtml = buildListHtml(
      availableItems,
      "No pantry matches found."
    );

    const printHtml = `
      <!doctype html>
      <html>
        <head>
          <meta charset="utf-8">
          <title>CulinaAI Shopping List</title>
          <style>
            @page {
              size: A4;
              margin: 18mm;
            }

            * {
              box-sizing: border-box;
            }

            body {
              margin: 0;
              color: #1f2937;
              font-family: Arial, sans-serif;
              line-height: 1.5;
            }

            .print-header {
              margin-bottom: 24px;
              padding-bottom: 14px;
              border-bottom: 2px solid #e5e7eb;
            }

            .print-label {
              margin: 0 0 8px;
              color: #15803d;
              font-size: 12px;
              font-weight: 800;
              letter-spacing: 0.08em;
              text-transform: uppercase;
            }

            h1 {
              margin: 0;
              color: #111827;
              font-size: 28px;
            }

            .recipe-title {
              margin: 8px 0 0;
              color: #4b5563;
              font-size: 15px;
              font-weight: 700;
            }

            h2 {
              margin: 22px 0 8px;
              color: #111827;
              font-size: 21px;
            }

            p {
              margin: 0 0 10px;
              color: #4b5563;
              font-size: 14px;
            }

            ul {
              margin: 8px 0 0 20px;
              padding: 0;
            }

            li {
              margin-bottom: 7px;
              font-size: 15px;
            }

            .note {
              margin-top: 26px;
              padding-top: 12px;
              border-top: 1px solid #e5e7eb;
              color: #6b7280;
              font-size: 12px;
            }
          </style>
        </head>

        <body>
          <div class="print-header">
            <p class="print-label">CulinaAI Pantry-Aware Shopping List</p>
            <h1>Shopping List</h1>
            <p class="recipe-title">${escapeHtml(recipeTitle)}</p>
          </div>

          <h2>Need to Buy</h2>
          ${missingHtml}

          <h2>Already in Pantry</h2>
          ${availableHtml}

          <p class="note">
            Generated by CulinaAI using the saved recipe and Smart Pantry comparison.
          </p>

          <script>
            window.onload = function () {
              window.focus();
              window.print();
              window.close();
            };
          <\/script>
        </body>
      </html>
    `;

    printWindow.document.open();
    printWindow.document.write(printHtml);
    printWindow.document.close();
  }

  if (copyButton) {
    copyButton.addEventListener("click", copyShoppingList);
  }

  if (printButton) {
    printButton.addEventListener("click", printShoppingList);
  }
});