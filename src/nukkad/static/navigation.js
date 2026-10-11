/* Small History API adapter. Only view, walk ID and scroll position enter history. */
(function (root) {
  "use strict";
  const panels = {
    home: "home",
    neighbourhood: "setup",
    history: "history",
    settings: "settings",
    plan: "quest-form-panel",
    preview: "preview",
    note: "outcome",
    folder: "place-folder",
  };
  function createNavigation({ browser, resolve, render, onError }) {
    let revision = 0,
      loading = false,
      scrollTimer;
    const read = () => {
      const url = new URL(browser.location.href);
      const view = Object.hasOwn(panels, url.searchParams.get("view"))
        ? url.searchParams.get("view")
        : "home";
      return {
        view,
        walk: ["preview", "note"].includes(view)
          ? url.searchParams.get("walk")
          : null,
        ...(view === "folder" ? {place: url.searchParams.get("place")} : {}),
      };
    };
    const address = ({ view, walk, place }) => {
      const url = new URL(browser.location.href);
      url.search = "";
      url.hash = "";
      if (view !== "home") url.searchParams.set("view", view);
      if (walk) url.searchParams.set("walk", walk);
      if (place) url.searchParams.set("place", place);
      return url.pathname + url.search;
    };
    const saveScroll = () => {
      if (loading) return;
      browser.history.replaceState(
        { ...read(), nukkad: true, scrollY: browser.scrollY },
        "",
        browser.location.href,
      );
    };
    async function apply(route, scrollY, supplied, anchor) {
      const token = ++revision;
      const current = () => token === revision;
      loading = true;
      clearTimeout(scrollTimer);
      try {
        const resolved = await resolve(route, current, supplied);
        if (!current()) return;
        if (resolved.view !== route.view || resolved.walk !== route.walk || resolved.place !== route.place) {
          browser.history.replaceState(
            {
              view: resolved.view,
              walk: resolved.walk,
              ...(resolved.view === "folder" ? {place: resolved.place} : {}),
              nukkad: true,
              scrollY: 0,
            },
            "",
            address(resolved),
          );
          scrollY = 0;
        }
        await render(resolved, current);
        if (!current()) return;
        const target = anchor && browser.document?.getElementById(anchor);
        if (target && !scrollY)
          target.scrollIntoView({ block: "start", behavior: "instant" });
        else browser.scrollTo({ top: scrollY, behavior: "instant" });
      } catch (error) {
        if (current()) onError(error);
      } finally {
        if (current()) loading = false;
      }
    }
    browser.history.scrollRestoration = "manual";
    browser.addEventListener(
      "scroll",
      () => {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(saveScroll, 80);
      },
      { passive: true },
    );
    browser.addEventListener("popstate", () => {
      const scrollY = browser.history.state?.scrollY || 0;
      void apply(read(), scrollY);
    });
    return {
      start() {
        const route = read();
        const y = browser.history.state?.scrollY || 0;
        browser.history.replaceState(
          { ...route, nukkad: true, scrollY: y },
          "",
          browser.location.href,
        );
        return apply(route, y, undefined, browser.location.hash?.slice(1));
      },
      go(panel, walk = null, supplied) {
        const view = Object.keys(panels).find((name) => panels[name] === panel);
        if (!view) throw Error("Unknown screen");
        const route = {
          view,
          walk: ["preview", "note"].includes(view) ? walk : null,
          ...(view === "folder" ? {place: walk} : {}),
        };
        const previous = read();
        if (previous.view === route.view && previous.walk === route.walk && previous.place === route.place)
          return Promise.resolve();
        saveScroll();
        browser.history.pushState(
          { ...route, nukkad: true, scrollY: 0 },
          "",
          address(route),
        );
        return apply(route, 0, supplied);
      },
      checkpoint() {
        const token = revision;
        return () => token === revision;
      },
      isCurrent(view, walk = null) {
        const route = read();
        return route.view === view && (!walk || (view === "folder" ? route.place === walk : route.walk === walk));
      },
    };
  }
  root.NukkadNavigation = { createNavigation, panels };
  if (typeof module !== "undefined") module.exports = root.NukkadNavigation;
})(globalThis);
