/* ==================================================
   PUBLIC WEBSITE JAVASCRIPT
================================================== */


/* ==================================================
   MOBILE MENU
================================================== */

function togglePublicMenu() {

    const menu =
        document.getElementById("mobilePublicNav");

    if (!menu) {
        return;
    }

    const button =
        document.querySelector(".mobile-menu-button");

    if (menu.style.display === "flex") {

        menu.style.display = "none";
        button?.setAttribute("aria-expanded", "false");

    } else {

        menu.style.display = "flex";
        button?.setAttribute("aria-expanded", "true");

    }

}


/* ==================================================
   CLOSE MOBILE MENU AFTER CLICKING A LINK
================================================== */

document.addEventListener(
    "DOMContentLoaded",
    function () {

        const menu =
            document.getElementById("mobilePublicNav");

        if (!menu) {
            return;
        }

        const links =
            menu.querySelectorAll("a");

        links.forEach(
            function (link) {

                link.addEventListener(
                    "click",
                    function () {

                        menu.style.display =
                            "none";

                    }
                );

            }
        );

    }
);


/* ==================================================
   ANNOUNCEMENT POPUP
================================================== */

function openAnnouncementModal() {

    const modal =
        document.getElementById(
            "announcementModal"
        );

    if (!modal) {
        return;
    }

    modal.classList.add("active");

    document.body.style.overflow =
        "hidden";

}


function closeAnnouncementModal() {

    const modal =
        document.getElementById(
            "announcementModal"
        );

    if (!modal) {
        return;
    }

    modal.classList.remove("active");

    document.body.style.overflow =
        "";

}


/* ==================================================
   CLOSE POPUP WHEN CLICKING OUTSIDE
================================================== */

document.addEventListener(
    "click",
    function (event) {

        const modal =
            document.getElementById(
                "announcementModal"
            );

        if (!modal) {
            return;
        }

        if (event.target === modal) {

            closeAnnouncementModal();

        }

    }
);


/* ==================================================
   ESC KEY
================================================== */

document.addEventListener(
    "keydown",
    function (event) {

        if (event.key !== "Escape") {
            return;
        }

        closeAnnouncementModal();

    }
);


/* ==================================================
   AUTOMATIC ANNOUNCEMENT POPUP
================================================== */

document.addEventListener(
    "DOMContentLoaded",
    function () {

        const modal =
            document.getElementById(
                "announcementModal"
            );

        if (!modal) {
            return;
        }

        const shouldShow =
            modal.dataset.show === "true";

        if (shouldShow) {

            setTimeout(
                function () {

                    openAnnouncementModal();

                },
                500
            );

        }

    }
);


/* ==================================================
   CURRENT YEAR
================================================== */

document.addEventListener(
    "DOMContentLoaded",
    function () {

        const yearElement =
            document.getElementById(
                "currentYear"
            );

        if (!yearElement) {
            return;
        }

        yearElement.textContent =
            new Date().getFullYear();

    }
);