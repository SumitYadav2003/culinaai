"""
The pieces that make CulinaAI installable and usable offline:

- /sw.js: the service worker (templates/pwa/sw.js). It has to be served from the
  site's root, not /static/, to look after every page.
- /manifest.webmanifest: the name, colours and icons used when it's installed.
- /offline/: the page shown offline for anything not saved on the device.

Change SW_VERSION when sw.js changes, so phones pick up the new version and
clear the old saved files.
"""

from django.shortcuts import render
from django.views.decorators.cache import cache_control

SW_VERSION = "culina-sw-1"


@cache_control(no_cache=True, max_age=0)
def service_worker_view(request):
    response = render(request, "pwa/sw.js", {"version": SW_VERSION}, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


@cache_control(max_age=60 * 60)
def manifest_view(request):
    return render(request, "pwa/manifest.webmanifest", content_type="application/manifest+json")


def offline_view(request):
    return render(request, "pwa/offline.html")
