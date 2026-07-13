/* =========================================================
   CULINAAI PREMIUM RECIPE OUTPUT FORMATTER
   Purpose:
   - Reads plain AI recipe text.
   - Converts it into cards, badges, icons and step sections.
   - Does not change backend AI generation logic.
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    const outputBlocks = document.querySelectorAll("[data-culina-recipe-output]");

    outputBlocks.forEach(function (outputBlock) {
        const rawText = outputBlock.innerText || outputBlock.textContent || "";

        if (!rawText.trim()) {
            return;
        }

        const sections = parseRecipeSections(rawText);

        if (!sections.length) {
            return;
        }

       const recipeBook = buildRecipeBook(sections);

attachSideImageToRecipeBook(outputBlock, recipeBook);

outputBlock.innerHTML = "";
outputBlock.appendChild(recipeBook);
    });
});



function attachSideImageToRecipeBook(outputBlock, recipeBook) {
    const imageCard = outputBlock.previousElementSibling;

    if (!imageCard || !imageCard.matches("[data-culina-recipe-image]")) {
        return;
    }

    const heroCard = recipeBook.querySelector(".culina-recipe-hero-card");

    if (!heroCard) {
        return;
    }

    const imageHeroLayout = document.createElement("div");
    imageHeroLayout.className = "culina-recipe-image-hero-layout";

    imageCard.remove();
    heroCard.remove();

    imageHeroLayout.appendChild(imageCard);
    imageHeroLayout.appendChild(heroCard);

    recipeBook.prepend(imageHeroLayout);
}


function parseRecipeSections(rawText) {
    const sectionHeadings = [
        "RECIPE TITLE",
        "SHORT DESCRIPTION",
        "MATCH SUMMARY",
        "INGREDIENTS WITH QUANTITIES",
        "COOKING TIME",
        "SERVINGS",
        "DIFFICULTY",
        "STEPS",
        "ALLERGY AND DIET NOTES",
        "ESTIMATED COST",
        "PAIRING SUGGESTIONS",
        "CHEF TIPS",
        "STORAGE ADVICE",
        "SUBSTITUTIONS"
    ];

    const lines = rawText
        .split(/\r?\n/)
        .map(function (line) {
            return line.trim();
        })
        .filter(function (line) {
            return line.length > 0;
        });

    const sections = [];
    let currentSection = null;

    lines.forEach(function (line) {
        const normalisedLine = line.replace(/:$/, "").trim().toUpperCase();

        if (sectionHeadings.includes(normalisedLine)) {
            currentSection = {
                heading: normalisedLine,
                items: []
            };

            sections.push(currentSection);
            return;
        }

        if (!currentSection) {
            currentSection = {
                heading: "RECIPE OVERVIEW",
                items: []
            };

            sections.push(currentSection);
        }

        currentSection.items.push(line);
    });

    return sections;
}


function buildRecipeBook(sections) {
    const book = document.createElement("div");
    book.className = "culina-recipe-book";

    const titleSection = findSection(sections, "RECIPE TITLE");
    const descriptionSection = findSection(sections, "SHORT DESCRIPTION");
    const cookingTimeSection = findSection(sections, "COOKING TIME");
    const servingsSection = findSection(sections, "SERVINGS");
    const difficultySection = findSection(sections, "DIFFICULTY");

    book.appendChild(
        buildHeroCard(
            getFirstItem(titleSection, "Personalised CulinaAI Recipe"),
            getJoinedText(descriptionSection),
            getFirstItem(cookingTimeSection, "Not specified"),
            getFirstItem(servingsSection, "Not specified"),
            getFirstItem(difficultySection, "Not specified")
        )
    );

    sections.forEach(function (section) {
        const hiddenHeadings = [
            "RECIPE TITLE",
            "SHORT DESCRIPTION",
            "COOKING TIME",
            "SERVINGS",
            "DIFFICULTY"
        ];

        if (hiddenHeadings.includes(section.heading)) {
            return;
        }

        book.appendChild(buildSectionCard(section));
    });

    return book;
}


function buildHeroCard(title, description, cookingTime, servings, difficulty) {
    const hero = document.createElement("div");
    hero.className = "culina-recipe-hero-card";

    hero.innerHTML = `
        <div class="culina-recipe-top-badge">
            <i class="bi bi-stars"></i>
            Final AI Recipe
        </div>

        <h2 class="culina-recipe-title">${escapeHtml(title)}</h2>

        <p class="culina-recipe-description">
            ${escapeHtml(description || "A personalised recipe prepared by CulinaAI based on the selected ingredients and preferences.")}
        </p>

        <div class="culina-recipe-summary-grid">
            <div class="culina-summary-pill">
                <i class="bi bi-clock-history"></i>
                <div>
                    <span>Cooking Time</span>
                    <strong>${escapeHtml(cookingTime)}</strong>
                </div>
            </div>

            <div class="culina-summary-pill">
                <i class="bi bi-people"></i>
                <div>
                    <span>Servings</span>
                    <strong>${escapeHtml(servings)}</strong>
                </div>
            </div>

            <div class="culina-summary-pill">
                <i class="bi bi-speedometer2"></i>
                <div>
                    <span>Difficulty</span>
                    <strong>${escapeHtml(difficulty)}</strong>
                </div>
            </div>
        </div>
    `;

    return hero;
}


function buildSectionCard(section) {
    const config = getSectionConfig(section.heading);

    const card = document.createElement("div");
    card.className = `culina-recipe-section-card ${config.extraClass}`;

    const header = document.createElement("div");
    header.className = "culina-recipe-section-header";
    header.innerHTML = `
        <div class="culina-section-icon">
            <i class="bi ${config.icon}"></i>
        </div>

        <div>
            <span>${escapeHtml(config.label)}</span>
            <h3>${escapeHtml(config.title)}</h3>
        </div>
    `;

    card.appendChild(header);

    if (!section.items.length) {
        const emptyNote = document.createElement("div");
        emptyNote.className = "culina-recipe-empty-note";
        emptyNote.textContent = "No details provided for this section.";
        card.appendChild(emptyNote);
        return card;
    }

    if (section.heading === "STEPS") {
        card.appendChild(buildSteps(section.items));
        return card;
    }

    if (shouldUseList(section.heading, section.items)) {
        card.appendChild(buildList(section.items, config.listIcon));
        return card;
    }

    card.appendChild(buildTextPanel(section.items, config.panelClass));
    return card;
}


function buildSteps(items) {
    const stepsWrap = document.createElement("div");
    stepsWrap.className = "culina-step-list";

    items.forEach(function (item, index) {
        const cleanedStep = item.replace(/^\d+\.\s*/, "").trim();

        const step = document.createElement("div");
        step.className = "culina-step-card";

        step.innerHTML = `
            <div class="culina-step-number">${index + 1}</div>
            <p>${escapeHtml(cleanedStep)}</p>
        `;

        stepsWrap.appendChild(step);
    });

    return stepsWrap;
}


function buildList(items, iconClass) {
    const list = document.createElement("ul");
    list.className = "culina-recipe-list";

    items.forEach(function (item) {
        const cleanedItem = item.replace(/^-\s*/, "").trim();

        const li = document.createElement("li");
        li.innerHTML = `
            <span class="culina-list-dot">
                <i class="bi ${iconClass}"></i>
            </span>
            <span>${escapeHtml(cleanedItem)}</span>
        `;

        list.appendChild(li);
    });

    return list;
}


function buildTextPanel(items, extraClass) {
    const panel = document.createElement("div");
    panel.className = `culina-text-panel ${extraClass}`;

    items.forEach(function (item) {
        const paragraph = document.createElement("p");
        paragraph.textContent = item;
        panel.appendChild(paragraph);
    });

    return panel;
}


function getSectionConfig(heading) {
    const configMap = {
        "MATCH SUMMARY": {
            title: "Why this recipe matches your request",
            label: "Smart Match",
            icon: "bi-bullseye",
            listIcon: "bi-check2",
            extraClass: "",
            panelClass: "culina-safe-style"
        },
        "INGREDIENTS WITH QUANTITIES": {
            title: "Ingredients you will need",
            label: "Ingredient Basket",
            icon: "bi-basket2",
            listIcon: "bi-check2-circle",
            extraClass: "",
            panelClass: ""
        },
        "STEPS": {
            title: "Step-by-step cooking method",
            label: "Chef Guidance",
            icon: "bi-list-ol",
            listIcon: "bi-arrow-right",
            extraClass: "",
            panelClass: ""
        },
        "ALLERGY AND DIET NOTES": {
            title: "Allergy and diet notes",
            label: "Safety Check",
            icon: "bi-shield-check",
            listIcon: "bi-exclamation-circle",
            extraClass: "",
            panelClass: "culina-warning-style"
        },
        "ESTIMATED COST": {
            title: "Estimated cost breakdown",
            label: "Budget Insight",
            icon: "bi-cash-coin",
            listIcon: "bi-currency-pound",
            extraClass: "culina-money-style",
            panelClass: ""
        },
        "PAIRING SUGGESTIONS": {
            title: "Pairing suggestions",
            label: "Serve It With",
            icon: "bi-cup-hot",
            listIcon: "bi-stars",
            extraClass: "culina-pairing-style",
            panelClass: ""
        },
        "CHEF TIPS": {
            title: "Chef tips",
            label: "Pro Cooking Advice",
            icon: "bi-lightbulb",
            listIcon: "bi-magic",
            extraClass: "culina-tips-style",
            panelClass: ""
        },
        "STORAGE ADVICE": {
            title: "Storage advice",
            label: "Keep It Fresh",
            icon: "bi-box-seam",
            listIcon: "bi-archive",
            extraClass: "",
            panelClass: "culina-safe-style"
        },
        "SUBSTITUTIONS": {
            title: "Substitutions",
            label: "Flexible Alternatives",
            icon: "bi-arrow-repeat",
            listIcon: "bi-arrow-left-right",
            extraClass: "",
            panelClass: ""
        },
        "RECIPE OVERVIEW": {
            title: "Recipe overview",
            label: "CulinaAI Notes",
            icon: "bi-journal-text",
            listIcon: "bi-dot",
            extraClass: "",
            panelClass: ""
        }
    };

    return configMap[heading] || {
        title: titleCase(heading),
        label: "Recipe Section",
        icon: "bi-journal-richtext",
        listIcon: "bi-check2",
        extraClass: "",
        panelClass: ""
    };
}


function shouldUseList(heading, items) {
    const listSections = [
        "INGREDIENTS WITH QUANTITIES",
        "ESTIMATED COST",
        "PAIRING SUGGESTIONS",
        "CHEF TIPS",
        "SUBSTITUTIONS"
    ];

    if (listSections.includes(heading)) {
        return true;
    }

    return items.every(function (item) {
        return item.startsWith("-");
    });
}


function findSection(sections, heading) {
    return sections.find(function (section) {
        return section.heading === heading;
    });
}


function getFirstItem(section, fallback) {
    if (!section || !section.items.length) {
        return fallback;
    }

    return section.items[0];
}


function getJoinedText(section) {
    if (!section || !section.items.length) {
        return "";
    }

    return section.items.join(" ");
}


function titleCase(text) {
    return text
        .toLowerCase()
        .split(" ")
        .map(function (word) {
            return word.charAt(0).toUpperCase() + word.slice(1);
        })
        .join(" ");
}


function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
}