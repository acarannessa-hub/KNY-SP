/* Ledger pages: search, add/edit/delete dialogs, Google Sheet sync badge. */
(function () {
    "use strict";

    var cfg = window.LEDGER || {};
    var peso = new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" });

    function $(id) { return document.getElementById(id); }

    // ---------------- dialogs ----------------
    function openDialog(dialog) {
        if (typeof dialog.showModal === "function") { dialog.showModal(); }
        else { dialog.setAttribute("open", ""); }
    }
    function closeDialog(dialog) {
        if (typeof dialog.close === "function") { dialog.close(); }
        else { dialog.removeAttribute("open"); }
    }
    document.querySelectorAll("[data-close]").forEach(function (button) {
        button.addEventListener("click", function () { closeDialog(button.closest("dialog")); });
    });
    document.querySelectorAll("[data-open]").forEach(function (button) {
        button.addEventListener("click", function () { openDialog($(button.dataset.open)); });
    });
    // click on the dark backdrop closes a dialog
    document.querySelectorAll("dialog").forEach(function (dialog) {
        dialog.addEventListener("click", function (event) {
            if (event.target === dialog) { closeDialog(dialog); }
        });
    });

    // ---------------- search + live totals ----------------
    var table = $("ledger-table");
    var rows = table ? Array.prototype.slice.call(table.querySelectorAll("tbody tr[data-id]")) : [];
    var search = $("ledger-search");

    function applySearch() {
        var query = (search.value || "").trim().toLowerCase();
        var shown = 0, total = 0;
        rows.forEach(function (row) {
            var hit = !query || row.dataset.search.indexOf(query) !== -1;
            row.hidden = !hit;
            if (hit) { shown += 1; total += parseFloat(row.dataset.amount) || 0; }
        });
        $("stat-count").textContent = shown;
        $("stat-total").textContent = peso.format(total);
        $("ledger-showing").textContent = query ? "Showing " + shown + " of " + rows.length : "";
        $("no-results").hidden = !(query && shown === 0 && rows.length);
    }
    if (search) { search.addEventListener("input", applySearch); }

    var duesSearch = $("dues-search");
    if (duesSearch) {
        duesSearch.addEventListener("input", function () {
            var query = duesSearch.value.trim().toLowerCase();
            document.querySelectorAll("#dues-table tbody tr").forEach(function (row) {
                row.hidden = query && row.dataset.search.indexOf(query) === -1;
            });
        });
    }

    // ---------------- member picker (membership fees) ----------------
    var memberSearch = $("member_search");
    var memberSelect = $("f_membership_id");
    function filterMembers() {
        var query = memberSearch.value.trim().toLowerCase();
        Array.prototype.forEach.call(memberSelect.options, function (option) {
            option.hidden = query && option.dataset.search.indexOf(query) === -1;
        });
    }
    if (memberSearch && memberSelect) { memberSearch.addEventListener("input", filterMembers); }

    // ---------------- add / edit ----------------
    var recordDialog = $("record-dialog");
    var recordForm = $("record-form");

    function openRecord(values, id) {
        recordForm.reset();
        Array.prototype.forEach.call(recordForm.elements, function (element) {
            if (element.name && Object.prototype.hasOwnProperty.call(values, element.name)) {
                element.value = values[element.name];
            }
        });
        if (memberSearch) { memberSearch.value = ""; filterMembers(); }
        recordForm.action = id ? cfg.editUrl.replace("__ID__", id) : cfg.addUrl;
        $("record-dialog-title").textContent = (id ? "Edit " : "Add ") + cfg.noun;
        $("record-submit").textContent = id ? "Save changes" : "Add record";
        openDialog(recordDialog);
        var first = recordForm.querySelector("input:not([type=hidden]), select, textarea");
        if (first) { first.focus(); }
    }

    var addButton = document.querySelector("[data-action=add]");
    if (addButton) { addButton.addEventListener("click", function () { openRecord({}, null); }); }

    // ---------------- row buttons ----------------
    var deleteDialog = $("delete-dialog");
    if (table) {
        table.addEventListener("click", function (event) {
            var button = event.target.closest("[data-action]");
            if (!button) { return; }
            var row = button.closest("tr");
            if (button.dataset.action === "edit") {
                openRecord(JSON.parse(row.dataset.record), row.dataset.id);
            } else if (button.dataset.action === "delete") {
                var headings = table.querySelectorAll("thead th");
                var parts = [];
                Array.prototype.forEach.call(row.cells, function (cell, index) {
                    var text = cell.textContent.trim();
                    var label = headings[index] ? headings[index].textContent.trim() : "";
                    if (text && text !== "—" && label && index < row.cells.length - 1) {
                        parts.push(label + ": " + text);
                    }
                });
                $("delete-summary").textContent = parts.join(" · ");
                $("delete-form").action = cfg.deleteUrl.replace("__ID__", row.dataset.id);
                openDialog(deleteDialog);
            }
        });
    }

    // ---------------- Google Sheet sync badge ----------------
    var badge = $("sync-badge");
    if (badge && cfg.statusUrl) {
        fetch(cfg.statusUrl, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
            .then(function (response) { return response.json(); })
            .then(function (status) {
                var detail = $("sync-detail");
                var item = (status.ledgers || [])[0] || {};
                badge.classList.remove("is-checking");
                badge.title = status.checked_at ? "Checked " + new Date(status.checked_at).toLocaleString() : "";
                if (status.ok) {
                    badge.textContent = "In sync";
                    badge.classList.add("is-ok");
                    return;
                }
                badge.classList.add("is-warn");
                var lines = [];
                if (item.error || status.error) {
                    badge.textContent = "Needs resync";
                    lines.push("The Google Sheet could not be compared: " + (item.error || status.error));
                } else {
                    badge.textContent = "Out of sync";
                    if (item.missing_count) { lines.push(item.missing_count + " record(s) are missing from the sheet"); }
                    if (item.extra_count) { lines.push(item.extra_count + " row(s) are in the sheet but not in the database"); }
                    if (item.changed_count) { lines.push(item.changed_count + " row(s) were edited in the sheet"); }
                    if (item.unlabeled) { lines.push(item.unlabeled + " row(s) were typed into the sheet by hand"); }
                }
                detail.textContent = "Google Sheet does not match the database: " + lines.join("; ") +
                    ". The database is the official record. An administrator can press " +
                    "“Resync Google Sheet” on Financial Management to make the sheet match it.";
                detail.hidden = false;
            })
            .catch(function () {
                badge.classList.remove("is-checking");
                badge.textContent = "Could not check";
            });
    }
})();
