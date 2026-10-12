/* =========================================================
   CulinaAI recipe layout
   Reads the plain recipe text the AI writes (RECIPE TITLE:, STEPS: ...)
   and lays it out as a normal recipe: title and facts, ingredients next
   to the method, then a few short notes. Nothing is sent anywhere and
   the saved text is not changed.

   Options on the [data-culina-recipe-output] element:
   - data-title-shown  the page already shows the title, time and difficulty,
                       so only the description and servings are added here.
   If no headings are found, the text is left exactly as it is.
   ========================================================= */

document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-culina-recipe-output]").forEach(function (outputBlock) {
        const rawText = outputBlock.innerText || outputBlock.textContent || "";
        if (!rawText.trim()) {
            return;
        }

        const sections = parseRecipeSections(rawText);
        if (!sections.some(function (section) { return section.known; })) {
            return; // older recipes without headings stay as plain text
        }

        const imageCard = findImageCard(outputBlock);
        const card = buildRecipeCard(sections, {
            titleShown: outputBlock.hasAttribute("data-title-shown"),
            image: imageCard
        });

        // The old layout's classes carry heavy styles, so the block starts clean.
        outputBlock.innerHTML = "";
        outputBlock.className = "rc-ready";
        outputBlock.appendChild(card);
    });
});


/* The AI's headings, and the name each one gets on the page. */
const RECIPE_HEADINGS = {
    "RECIPE TITLE": "title",
    "MODIFIED RECIPE TITLE": "title",
    "SHORT DESCRIPTION": "description",
    "WHAT CHANGED": "changed",
    "MATCH SUMMARY": "match",
    "INGREDIENTS WITH QUANTITIES": "ingredients",
    "INGREDIENTS": "ingredients",
    "COOKING TIME": "time",
    "SERVINGS": "servings",
    "DIFFICULTY": "difficulty",
    "STEPS": "steps",
    "INSTRUCTIONS": "steps",
    "METHOD": "steps",
    "ALLERGY AND DIET NOTES": "allergy",
    "ESTIMATED COST": "cost",
    "PAIRING SUGGESTIONS": "pairing",
    "CHEF TIPS": "tips",
    "STORAGE ADVICE": "storage",
    "SUBSTITUTIONS": "swaps"
};

/* The sentence the generation prompt asks for, said in plain words. */
const STOCK_ALLERGY_LINE = /^the user-provided restricted ingredients have been excluded from this recipe\.?$/i;


function cleanHeading(line) {
    return line.replace(/^[#*\s]+/, "").replace(/[*\s]+$/, "").replace(/\*+/g, "").trim();
}


function parseRecipeSections(rawText) {
    const sections = [];
    let current = null;

    rawText.split(/\r?\n/).forEach(function (rawLine) {
        const line = rawLine.trim();
        if (!line) {
            return;
        }

        // "COOKING TIME:" on its own line, or "COOKING TIME: 25 minutes".
        const match = cleanHeading(line).match(/^([A-Za-z /&]+?)\s*:\s*(.*)$/);
        const heading = match ? match[1].toUpperCase() : cleanHeading(line).replace(/:$/, "").toUpperCase();
        const key = RECIPE_HEADINGS[heading];

        if (key && (match || cleanHeading(line).toUpperCase() === heading)) {
            current = { key: key, known: true, items: [] };
            sections.push(current);
            const rest = match ? match[2].replace(/\*+/g, "").trim() : "";
            if (rest) {
                current.items.push(rest);
            }
            return;
        }

        if (!current) {
            current = { key: "intro", known: false, items: [] };
            sections.push(current);
        }
        current.items.push(line);
    });

    return sections;
}


function section(sections, key) {
    return sections.find(function (s) { return s.key === key; });
}

function firstLine(sections, key) {
    const found = section(sections, key);
    return found && found.items.length ? found.items[0] : "";
}

function joined(sections, key) {
    const found = section(sections, key);
    return found ? found.items.join(" ") : "";
}

function stripBullet(text) {
    return text.replace(/^([-•*]|\d+[.)])\s*/, "").trim();
}

function servingsText(value) {
    const clean = value.replace(/\.$/, "").trim();
    if (/^\d+$/.test(clean)) {
        return "Serves " + clean;
    }
    if (/^\d+\s+servings?$/i.test(clean)) {
        return "Serves " + clean.split(/\s+/)[0];
    }
    return clean;
}

function capitalise(value) {
    const clean = value.replace(/\.$/, "").trim();
    return clean.charAt(0).toUpperCase() + clean.slice(1);
}


function findImageCard(outputBlock) {
    const before = outputBlock.previousElementSibling;
    if (before && before.matches("[data-culina-recipe-image]")) {
        return before;
    }
    return null;
}


function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) {
        node.className = className;
    }
    if (text !== undefined) {
        node.textContent = text;
    }
    return node;
}

function iconItem(icon, text) {
    const li = el("li");
    const i = el("i", icon);
    i.setAttribute("aria-hidden", "true");
    li.appendChild(i);
    li.appendChild(document.createTextNode(" " + text));
    return li;
}


function buildRecipeCard(sections, options) {
    const card = el("article", "rc");

    /* Title, description and facts */
    const head = el("header", "rc-head");
    if (options.image) {
        options.image.remove();
        options.image.className = "rc-image";
        head.classList.add("rc-head-with-image");
        head.appendChild(options.image);
    }

    const headText = el("div", "rc-head-text");
    const title = firstLine(sections, "title");
    if (title && !options.titleShown) {
        headText.appendChild(el("h2", "rc-title", title.replace(/\*+/g, "")));
    }

    const description = joined(sections, "description");
    if (description) {
        headText.appendChild(el("p", "rc-desc", description));
    }

    const facts = el("ul", "rc-facts");
    const time = firstLine(sections, "time");
    const servings = firstLine(sections, "servings");
    const difficulty = firstLine(sections, "difficulty");
    if (time && !options.titleShown) {
        facts.appendChild(iconItem("icon-clock", time.replace(/\.$/, "")));
    }
    if (servings) {
        facts.appendChild(iconItem("icon-users", servingsText(servings)));
    }
    if (difficulty && !options.titleShown) {
        facts.appendChild(iconItem("icon-chart-column", capitalise(difficulty)));
    }
    if (facts.children.length) {
        headText.appendChild(facts);
    }

    const changed = joined(sections, "changed");
    if (changed) {
        const note = el("p", "rc-changed");
        note.appendChild(el("strong", "", "What changed: "));
        note.appendChild(document.createTextNode(changed));
        headText.appendChild(note);
    }

    if (headText.children.length || options.image) {
        head.appendChild(headText);
        card.appendChild(head);
    }

    /* Ingredients next to the method */
    const body = el("div", "rc-body");
    const ingredients = section(sections, "ingredients");
    if (ingredients && ingredients.items.length) {
        const block = el("section", "rc-ingredients");
        block.appendChild(el("h3", "", "Ingredients"));
        const list = el("ul", "rc-ingredient-list");
        ingredients.items.forEach(function (item) {
            const text = stripBullet(item);
            if (!text) {
                return;
            }
            // "For the sauce:" style sub-headings
            list.appendChild(el("li", /:$/.test(text) ? "rc-sub" : "", text));
        });
        block.appendChild(list);
        body.appendChild(block);
    }

    const steps = section(sections, "steps");
    if (steps && steps.items.length) {
        const block = el("section", "rc-method");
        block.appendChild(el("h3", "", "Method"));
        const list = el("ol", "rc-steps");
        steps.items.forEach(function (item) {
            const text = stripBullet(item);
            if (text) {
                list.appendChild(el("li", "", text));
            }
        });
        block.appendChild(list);
        body.appendChild(block);
    }

    // Text before any heading (older recipes): show it as plain paragraphs.
    const intro = section(sections, "intro");
    if (intro && intro.items.length && !(steps && steps.items.length)) {
        const block = el("section", "rc-method");
        intro.items.forEach(function (item) { block.appendChild(el("p", "", item)); });
        body.appendChild(block);
    }

    if (body.children.length) {
        card.appendChild(body);
    }

    /* Short notes underneath */
    const notes = [
        ["tips", "Tips"],
        ["swaps", "Swaps"],
        ["pairing", "Serve it with"],
        ["storage", "Leftovers"],
        ["allergy", "Allergies and diet"],
        ["match", "Why it suits you"]
    ];
    const extras = el("div", "rc-notes");
    notes.forEach(function (pair) {
        const found = section(sections, pair[0]);
        if (!found || !found.items.length) {
            return;
        }
        const block = el("section", "rc-note");
        block.appendChild(el("h3", "", pair[1]));
        const items = found.items.map(function (item) {
            return STOCK_ALLERGY_LINE.test(item.trim())
                ? "Anything you said you can't eat has been left out. Always check the labels."
                : item;
        });
        if (items.length > 1 || /^[-•*]/.test(items[0])) {
            const list = el("ul", "");
            items.forEach(function (item) {
                const text = stripBullet(item);
                if (text) {
                    list.appendChild(el("li", "", text));
                }
            });
            block.appendChild(list);
        } else {
            block.appendChild(el("p", "", items[0]));
        }
        extras.appendChild(block);
    });
    if (extras.children.length) {
        card.appendChild(extras);
    }

    // The AI's own cost guess is left out: the cost shown under the recipe is
    // worked out from real shop prices, and two different figures would confuse.
    return card;
}
