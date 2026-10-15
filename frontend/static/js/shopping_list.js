/* =========================================================
   Shopping list: tick items without reloading the page, copy
   the list as text, and keep ticks made with no signal.

   Offline: a tick is shown straight away and kept on this device
   (localStorage). When the connection comes back, the kept ticks
   are sent in order. Each one says "ticked" or "not ticked"
   (done=1 / done=0), so sending one twice does no harm.

   Without JavaScript the tick buttons still work as normal forms.
   ========================================================= */

(function () {
    "use strict";

    const QUEUE_KEY = "culina-shopping-queue";
    const doneCount = document.querySelector("[data-done-count]");
    const queueNote = document.querySelector("[data-queue-note]");

    function readQueue() {
        try {
            return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
        } catch (error) {
            return [];
        }
    }

    function writeQueue(queue) {
        try {
            if (queue.length) {
                localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
            } else {
                localStorage.removeItem(QUEUE_KEY);
            }
        } catch (error) {
            /* storage blocked: the tick still shows, it just can't be kept */
        }
        showQueueNote(queue.length);
    }

    function showQueueNote(count) {
        if (!queueNote) {
            return;
        }
        queueNote.hidden = count === 0;
        queueNote.textContent =
            count === 1
                ? "1 tick is saved on this device and will be sent when you're back online."
                : count + " ticks are saved on this device and will be sent when you're back online.";
    }

    function updateCount(change) {
        if (!doneCount) {
            return;
        }
        doneCount.textContent = Math.max(0, (Number(doneCount.textContent) || 0) + change);
    }

    function setItem(item, done) {
        item.classList.toggle("is-done", done);
        const box = item.querySelector(".mp-box");
        if (box) {
            box.setAttribute("aria-checked", String(done));
        }
    }

    function send(entry) {
        const data = new FormData();
        Object.keys(entry.fields).forEach(function (name) {
            data.append(name, entry.fields[name]);
        });
        return fetch(entry.url, {
            method: "POST",
            body: data,
            headers: { "X-Requested-With": "fetch" },
            credentials: "same-origin",
        }).then(function (response) {
            if (!response.ok) {
                const error = new Error("Not saved");
                error.status = response.status;
                throw error;
            }
            return response.json();
        });
    }

    // One tick at a time, oldest first; stop at the first failure and try again later.
    let flushing = false;
    function flushQueue() {
        if (flushing || !navigator.onLine) {
            return;
        }
        const queue = readQueue();
        if (!queue.length) {
            showQueueNote(0);
            return;
        }
        flushing = true;
        send(queue[0])
            .then(function () {
                writeQueue(readQueue().slice(1));
                flushing = false;
                flushQueue();
            })
            .catch(function (error) {
                flushing = false;
                // The server refused it (logged out, or the item went): drop it rather than retry forever.
                if (error.status && error.status < 500) {
                    writeQueue(readQueue().slice(1));
                    flushQueue();
                }
            });
    }

    document.querySelectorAll("[data-tick-form]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            event.preventDefault();

            const item = form.closest(".mp-item");
            const wasDone = item.classList.contains("is-done");
            const fields = {};
            new FormData(form).forEach(function (value, name) {
                fields[name] = value;
            });
            fields.done = wasDone ? "0" : "1";
            const entry = { url: form.action, fields: fields };

            // Show the change straight away.
            setItem(item, !wasDone);
            updateCount(wasDone ? -1 : 1);

            if (!navigator.onLine || readQueue().length) {
                // Offline (or older ticks still waiting): keep it, in order.
                writeQueue(readQueue().concat([entry]));
                flushQueue();
                return;
            }

            send(entry)
                .then(function (data) {
                    // If it was changed somewhere else (another tab or phone), show what was saved.
                    if (data.done !== !wasDone) {
                        setItem(item, data.done);
                        updateCount(data.done ? 1 : -1);
                    }
                })
                .catch(function (error) {
                    if (!error.status) {
                        // No connection after all: keep it for later.
                        writeQueue(readQueue().concat([entry]));
                    } else {
                        // The server said no: undo, so the page shows what's really saved.
                        setItem(item, wasDone);
                        updateCount(wasDone ? 1 : -1);
                    }
                });
        });
    });

    // Ticks kept from an earlier visit: show them on the page, then send them when possible.
    readQueue().forEach(function (entry) {
        document.querySelectorAll("[data-tick-form]").forEach(function (form) {
            if (form.action !== entry.url) {
                return;
            }
            const key = form.querySelector("[name=key]");
            const week = form.querySelector("[name=week]");
            const sameItem = (!key || key.value === entry.fields.key) && (!week || week.value === entry.fields.week);
            if (sameItem) {
                const item = form.closest(".mp-item");
                const done = entry.fields.done === "1";
                if (item.classList.contains("is-done") !== done) {
                    setItem(item, done);
                    updateCount(done ? 1 : -1);
                }
            }
        });
    });
    showQueueNote(readQueue().length);
    window.addEventListener("online", flushQueue);
    flushQueue();

    // ---------- Copy as text ----------

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
