(function () {
  const HIDDEN_NAV_PAGES = new Set(["detail.html", "fuzzy.html", "tracking.html", "login.html"]);

  function hasParentRouter() {
    try {
      return window.parent && window.parent !== window && typeof window.parent.changeChannel === "function";
    } catch (error) {
      return false;
    }
  }

  function currentPageName() {
    const parts = window.location.pathname.split("/");
    return parts[parts.length - 1] || "home.html";
  }

  window.isEmbeddedApp = hasParentRouter;

  window.navigateTo = function navigateTo(url, tabId) {
    if (hasParentRouter()) {
      window.parent.changeChannel(url, tabId);
      return;
    }
    window.location.href = url;
  };

  window.navigateToRoot = function navigateToRoot(url) {
    if (hasParentRouter()) {
      window.parent.location.href = url;
      return;
    }
    window.location.href = url;
  };

  window.setupStandaloneNav = function setupStandaloneNav(activeTabId) {
    const nav = document.getElementById("standalone-nav");
    if (!nav || hasParentRouter() || HIDDEN_NAV_PAGES.has(currentPageName())) {
      if (nav) {
        nav.classList.add("hidden");
      }
      return;
    }

    nav.classList.remove("hidden");
    nav.querySelectorAll("[data-tab]").forEach((item) => {
      item.classList.toggle("active", item.dataset.tab === activeTabId);
    });
  };
})();
