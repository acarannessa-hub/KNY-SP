/* Public site: mobile menu, "About" dropdown, footer year. */
(function () {
    "use strict";

    // Mobile menu
    var toggle = document.querySelector("[data-mobile-toggle]");
    var mobileNav = document.getElementById("mobile-nav");
    if (toggle && mobileNav) {
        toggle.addEventListener("click", function () {
            var open = mobileNav.hidden;
            mobileNav.hidden = !open;
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
        });
    }

    // "About" dropdown: click or keyboard to open; Escape / outside click closes
    document.querySelectorAll("[data-menu-button]").forEach(function (button) {
        var menu = document.getElementById(button.getAttribute("aria-controls"));
        if (!menu) { return; }
        function setOpen(open) {
            menu.hidden = !open;
            button.setAttribute("aria-expanded", open ? "true" : "false");
        }
        button.addEventListener("click", function (event) {
            event.stopPropagation();
            setOpen(menu.hidden);
            if (!menu.hidden) { var first = menu.querySelector("a"); if (first) { first.focus(); } }
        });
        document.addEventListener("click", function (event) {
            if (!menu.hidden && !menu.contains(event.target)) { setOpen(false); }
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && !menu.hidden) { setOpen(false); button.focus(); }
        });
        menu.addEventListener("focusout", function (event) {
            if (!menu.contains(event.relatedTarget) && event.relatedTarget !== button) { setOpen(false); }
        });
    });

    var year = document.getElementById("currentYear");
    if (year) { year.textContent = new Date().getFullYear(); }
})();

/* Section tabs: the page's sections become a row of tabs under the page head;
   the tab for the section being read is marked current. */
(function () {
    "use strict";
    var head = document.querySelector(".page-head");
    if (!head) { return; }
    var headings = Array.prototype.filter.call(
        document.querySelectorAll("main section h2, main article h2"),
        function (h) { return !h.classList.contains("sr-only") && !h.closest(".page-head") && !h.closest(".site-footer"); }
    );
    if (headings.length < 2) { return; }

    var strip = document.createElement("nav");
    strip.className = "section-tabs";
    strip.setAttribute("aria-label", "Sections on this page");
    var wrap = document.createElement("div");
    wrap.className = "wrap";
    var label = document.createElement("span");
    label.className = "section-tabs-label";
    label.textContent = "On this page";
    wrap.appendChild(label);
    var list = document.createElement("ul");
    var links = [];
    headings.forEach(function (h, i) {
        var holder = h.closest("article[id]");
        if (!h.id && !holder) { h.id = "section-" + (i + 1); }
        h.dataset.anchor = holder ? holder.id : h.id;
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.href = "#" + h.dataset.anchor;
        a.textContent = h.textContent.replace(/\s+/g, " ").trim().replace(/^\[|\]$/g, "").slice(0, 34);
        li.appendChild(a);
        list.appendChild(li);
        links.push(a);
    });
    wrap.appendChild(list);
    strip.appendChild(wrap);
    head.insertAdjacentElement("afterend", strip);

    var tocLinks = document.querySelectorAll(".doc-toc a");
    function mark(index) {
        links.forEach(function (a, i) {
            if (i === index) { a.setAttribute("aria-current", "true"); } else { a.removeAttribute("aria-current"); }
        });
        var active = links[index];
        if (active && active.scrollIntoView && list.scrollWidth > list.clientWidth) {
            list.scrollTo({ left: active.parentNode.offsetLeft - list.offsetLeft - 8, behavior: "smooth" });
        }
        var id = headings[index] && headings[index].dataset.anchor;
        tocLinks.forEach(function (a) {
            if (a.getAttribute("href") === "#" + id) {
                a.setAttribute("aria-current", "true");
            } else { a.removeAttribute("aria-current"); }
        });
    }
    function update() {
        var line = 180, current = 0;
        headings.forEach(function (h, i) { if (h.getBoundingClientRect().top - line <= 0) { current = i; } });
        mark(current);
    }
    var ticking = false;
    window.addEventListener("scroll", function () {
        if (!ticking) { ticking = true; requestAnimationFrame(function () { update(); ticking = false; }); }
    }, { passive: true });
    update();
})();
