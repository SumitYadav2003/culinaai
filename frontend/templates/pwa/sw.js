{% load static %}/* CulinaAI service worker (served from /sw.js so it covers the whole site).

   What it does:
   - Keeps a copy of the shopping list, meal plan, recipe pages and cooking mode
     each time you open them online, so they still open without signal.
     It always tries the internet first; the saved copy is only used offline.
   - Keeps the site's CSS, JavaScript, fonts and icons, so saved pages look right offline.
   - Shows a simple "You're offline" page for anything that isn't saved.
   - Saved pages belong to one account. They are deleted when you log out, or
     when someone else logs in on the same device.

   It never saves anything you send (forms, ticks); the shopping list page queues
   ticks made offline itself (static/js/shopping_list.js). */

const VERSION = "{{ version }}";
const STATIC_CACHE = "culina-static-" + VERSION;
const META_CACHE = "culina-meta";
const PAGE_PREFIX = "culina-pages-";
const OFFLINE_URL = "{% url 'offline_page' %}";
const MAX_PAGES = 40;

// Pages worth having offline: the shopping list, the plan, a saved recipe and its cooking mode.
const SAVED_PAGES = [
    /^\/recipes\/shopping\/$/,
    /^\/recipes\/plan\/$/,
    /^\/recipes\/saved\/\d+\/$/,
    /^\/recipes\/saved\/\d+\/cook\/$/,
];

// Other sites the pages load files from (Bootstrap, the icon font, the web font).
const CDN_HOSTS = ["cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com"];

const PRECACHE = [
    OFFLINE_URL,
    "{% static 'images/logo.svg' %}",
    "{% static 'images/icons/icon-192.png' %}",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((names) => Promise.all(
                names
                    .filter((name) => name.startsWith("culina-static-") && name !== STATIC_CACHE)
                    .map((name) => caches.delete(name))
            ))
            .then(() => self.clients.claim())
    );
});

// ---------- Whose pages these are ----------

async function getUser() {
    const cache = await caches.open(META_CACHE);
    const saved = await cache.match("/__culina-user");
    return saved ? saved.text() : "";
}

async function setUser(id) {
    const cache = await caches.open(META_CACHE);
    await cache.put("/__culina-user", new Response(String(id)));
    // Someone else's saved pages never stay on the device.
    const names = await caches.keys();
    await Promise.all(
        names.filter((name) => name.startsWith(PAGE_PREFIX) && name !== PAGE_PREFIX + id).map((name) => caches.delete(name))
    );
}

async function forgetUser() {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith(PAGE_PREFIX)).map((name) => caches.delete(name)));
    await caches.delete(META_CACHE);
}

self.addEventListener("message", (event) => {
    const data = event.data || {};
    if (data.type === "user" && data.id) {
        event.waitUntil(setUser(data.id));
    } else if (data.type === "logout") {
        event.waitUntil(forgetUser());
    }
});

// ---------- Fetching ----------

function isSavedPage(url) {
    return url.origin === self.location.origin && SAVED_PAGES.some((pattern) => pattern.test(url.pathname));
}

async function trim(cache) {
    const keys = await cache.keys();
    for (let i = 0; i < keys.length - MAX_PAGES; i += 1) {
        await cache.delete(keys[i]);
    }
}

async function savedPageFirstOnline(request) {
    try {
        const response = await fetch(request);
        const user = await getUser();
        // Only keep real pages for the logged-in user (not a redirect to the login page).
        if (user && response.ok && !response.redirected && response.type === "basic") {
            const cache = await caches.open(PAGE_PREFIX + user);
            await cache.put(request, response.clone());
            trim(cache);
        }
        return response;
    } catch (error) {
        const user = await getUser();
        if (user) {
            const cache = await caches.open(PAGE_PREFIX + user);
            // The exact page, or failing that the same page for another week (the page says which week).
            const saved = (await cache.match(request)) || (await cache.match(request, { ignoreSearch: true }));
            if (saved) {
                return saved;
            }
        }
        return (await caches.match(OFFLINE_URL)) || Response.error();
    }
}

async function pageOrOffline(request) {
    try {
        return await fetch(request);
    } catch (error) {
        return (await caches.match(OFFLINE_URL)) || Response.error();
    }
}

async function staleWhileRevalidate(request) {
    const cache = await caches.open(STATIC_CACHE);
    const saved = await cache.match(request);
    const fresh = fetch(request)
        .then((response) => {
            if (response.ok || response.type === "opaque") {
                cache.put(request, response.clone());
            }
            return response;
        })
        .catch(() => saved);
    return saved || fresh;
}

self.addEventListener("fetch", (event) => {
    const request = event.request;
    if (request.method !== "GET") {
        return;
    }
    const url = new URL(request.url);

    if (request.mode === "navigate") {
        event.respondWith(isSavedPage(url) ? savedPageFirstOnline(request) : pageOrOffline(request));
        return;
    }

    const isOwnStatic = url.origin === self.location.origin && (url.pathname.startsWith("/static/") || url.pathname.startsWith("/media/"));
    if (isOwnStatic || CDN_HOSTS.includes(url.hostname)) {
        event.respondWith(staleWhileRevalidate(request));
    }
});
