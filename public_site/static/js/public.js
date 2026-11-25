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
