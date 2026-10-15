/* =========================================================
   Shopping list: tick items without reloading the page, and
   copy the list as text. Without JavaScript the tick buttons
   still work as normal form posts.
   ========================================================= */

(function () {
    "use strict";

    const doneCount = document.querySelector("[data-done-count]");

    function updateCount(change) {
        if (!doneCount) {
            return;
        }
        doneCount.textContent = Math.max(0, (Number(doneCount.textContent) || 0) + change);
    }

    document.querySelectorAll("[data-tick-form]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            event.preventDefault();

            const item = form.closest(".mp-item");
            const box = form.querySelector(".mp-box");
            const wasDone = item.classList.contains("is-done");

            // Show the change straight away; undo it if saving fails.
            item.classList.toggle("is-done", !wasDone);
            box.setAttribute("aria-checked", String(!wasDone));
            updateCount(wasDone ? -1 : 1);

            fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: { "X-Requested-With": "fetch" },
                credentials: "same-origin",
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("Not saved");
                    }
                    return response.json();
                })
                .then(function (data) {
                    // If the list was changed somewhere else (another tab or phone), show what was saved.
                    if (data.done === wasDone) {
                        item.classList.toggle("is-done", data.done);
                        box.setAttribute("aria-checked", String(data.done));
                        updateCount(data.done ? 1 : -1);
                    }
                })
                .catch(function () {
                    // Couldn't save: reload so the page shows what is really saved.
                    window.location.reload();
                });
        });
    });

    const copyButton = document.querySelector("[data-copy-list]");
    const listText = document.querySelector("[data-list-text]");

    if (copyButton && listText) {
        copyButton.addEventListener("click", function () {
            const label = copyButton.querySelector("span");
            const done = function () {
                label.textContent = "Copied";
                setTimeout(function () {
                    label.textContent = "Copy";
                }, 2000);
            };

            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(listText.value).then(done, function () {
                    listText.select();
                    document.execCommand("copy");
                    done();
                });
            } else {
                listText.select();
                document.execCommand("copy");
                done();
            }
        });
    }
})();
