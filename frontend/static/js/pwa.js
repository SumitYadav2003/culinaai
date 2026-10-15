/* =========================================================
   Install as an app, and work offline.

   - Registers the service worker (/sw.js), which keeps a copy of
     the shopping list, plan and recipes you open.
   - Tells it who is logged in, so saved pages are only ever one
     person's, and clears them on any logged-out page.
   - Shows a bar when you're offline, with the time the page was saved.
   - Shows "Install the app" where the browser allows it.
   ========================================================= */

(function () {
    "use strict";

    const body = document.body;
    const userId = body.dataset.userId || "";

    function clearSavedPages() {
        if (!("caches" in window)) {
            return;
        }
        caches.keys().then(function (names) {
            names
                .filter(function (name) {
                    return name.indexOf("culina-pages-") === 0 || name === "culina-meta";
                })
                .forEach(function (name) {
                    caches.delete(name);
                });
        });
        try {
            localStorage.removeItem("culina-shopping-queue");
        } catch (error) {
            /* storage may be blocked; nothing to clear then */
        }
    }

    if ("serviceWorker" in navigator) {
        window.addEventListener("load", function () {
            navigator.serviceWorker
                .register("/sw.js", { scope: "/" })
                .then(function () {
                    return navigator.serviceWorker.ready;
                })
                .then(function (registration) {
                    const worker = registration.active;
                    if (!worker) {
                        return;
                    }
                    worker.postMessage(userId ? { type: "user", id: userId } : { type: "logout" });
                })
                .catch(function () {
                    /* Offline support is a bonus; the site works without it. */
                });
        });
    }

    if (!userId) {
        clearSavedPages();
    }

    // ---------- "You're offline" bar ----------

    const bar = document.querySelector("[data-offline-bar]");
    const barText = bar ? bar.querySelector("[data-offline-text]") : null;

    function savedAt() {
        const stamp = body.dataset.renderedAt;
        const when = stamp ? new Date(stamp) : null;
        if (!when || isNaN(when)) {
            return "";
        }
        const sameDay = when.toDateString() === new Date().toDateString();
        const time = when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        return sameDay ? time : when.toLocaleDateString([], { day: "numeric", month: "short" }) + ", " + time;
    }

    function showOfflineState() {
        if (!bar) {
            return;
        }
        const offline = !navigator.onLine;
        bar.hidden = !offline;
        body.classList.toggle("is-offline", offline);
        if (offline && barText) {
            const at = savedAt();
            barText.textContent = "You're offline. Showing the copy saved on this device" + (at ? " at " + at : "") + ".";
        }
    }

    window.addEventListener("online", showOfflineState);
    window.addEventListener("offline", showOfflineState);
    showOfflineState();

    // ---------- Install the app ----------

    let installEvent = null;
    const installButtons = document.querySelectorAll("[data-install-app]");

    window.addEventListener("beforeinstallprompt", function (event) {
        event.preventDefault();
        installEvent = event;
        installButtons.forEach(function (button) {
            button.hidden = false;
        });
    });

    installButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            if (!installEvent) {
                return;
            }
            installEvent.prompt();
            installEvent.userChoice.finally(function () {
                installEvent = null;
                installButtons.forEach(function (other) {
                    other.hidden = true;
                });
            });
        });
    });

    window.addEventListener("appinstalled", function () {
        installButtons.forEach(function (button) {
            button.hidden = true;
        });
    });
})();
