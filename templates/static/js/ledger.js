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

    // ---------------- column dropdowns: sort + filter ----------------
    var table = $("ledger-table");
    var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var BLANK = "(blank)";

    function filterKey(kind, raw) {
        if (!raw) { return BLANK; }
        if (kind === "date") {
            var m = /^(\d{4})-(\d{2})/.exec(raw);
            return m ? m[1] + "-" + m[2] : raw;          // dates are grouped by month
        }
        return raw;
    }
    function keyLabel(kind, key) {
        if (kind === "date" && /^\d{4}-\d{2}$/.test(key)) {
            return MONTHS[parseInt(key.slice(5), 10) - 1] + " " + key.slice(0, 4);
        }
        return key;
    }

    var menu = document.createElement("div");
    menu.className = "col-menu";
    menu.hidden = true;
    menu.setAttribute("role", "dialog");
    menu.setAttribute("aria-label", "Sort and filter");
    document.body.appendChild(menu);
    var openState = null;     // {grid, col, button}

    function closeMenu(restoreFocus) {
        if (!openState) { return; }
        var button = openState.button;
        button.setAttribute("aria-expanded", "false");
        menu.hidden = true;
        openState = null;
        if (restoreFocus) { button.focus(); }
    }
    document.addEventListener("click", function (event) {
        if (openState && !menu.contains(event.target) && !openState.button.contains(event.target)) { closeMenu(false); }
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && openState) { closeMenu(true); }
    });
    window.addEventListener("resize", function () { closeMenu(false); });

    function FilterGrid(tableEl, onChange) {
        var grid = this;
        grid.table = tableEl;
        grid.onChange = onChange || function () {};
        // Only this table's own heading row and body rows (not nested tables).
        grid.headers = Array.prototype.slice.call(tableEl.tHead.rows[0].cells);
        grid.rows = Array.prototype.slice.call(tableEl.tBodies[0].rows).filter(function (row) {
            return row.cells.length && row.cells[0].hasAttribute("data-value");
        });
        grid.filters = {};      // column index -> Set of allowed values
        grid.sort = null;       // {col, dir}
        grid.headers.forEach(function (th, col) {
            var button = th.querySelector(".col-filter");
            if (!button) { return; }
            button.addEventListener("click", function (event) {
                event.stopPropagation();
                if (openState && openState.button === button) { closeMenu(true); return; }
                grid.openMenu(col, button);
            });
        });
    }

    FilterGrid.prototype.kind = function (col) { return this.headers[col].dataset.kind || "text"; };
    FilterGrid.prototype.cellRaw = function (row, col) {
        var cell = row.cells[col];
        return cell ? (cell.getAttribute("data-value") || "") : "";
    };
    FilterGrid.prototype.rowKey = function (row, col) { return filterKey(this.kind(col), this.cellRaw(row, col)); };
    FilterGrid.prototype.passes = function (row, skipCol) {
        var grid = this;
        return Object.keys(grid.filters).every(function (col) {
            return +col === skipCol || grid.filters[col].has(grid.rowKey(row, +col));
        });
    };

    FilterGrid.prototype.apply = function () {
        var grid = this;
        var visible = [];
        grid.rows.forEach(function (row) {
            var show = grid.passes(row, -1);
            row.hidden = !show;
            if (show) { visible.push(row); }
        });
        if (grid.sort) {
            var col = grid.sort.col, dir = grid.sort.dir, kind = grid.kind(col);
            var body = grid.table.tBodies[0];
            grid.rows.slice().sort(function (a, b) {
                var x = grid.cellRaw(a, col), y = grid.cellRaw(b, col);
                var cmp = kind === "money" ? (parseFloat(x) || 0) - (parseFloat(y) || 0)
                    : x.localeCompare(y, undefined, { numeric: true, sensitivity: "base" });
                return dir === "asc" ? cmp : -cmp;
            }).forEach(function (row) { body.appendChild(row); });
        }
        grid.headers.forEach(function (th, col) {
            th.classList.toggle("is-filtered", Object.prototype.hasOwnProperty.call(grid.filters, col));
            var sorted = !!grid.sort && grid.sort.col === col;
            th.classList.toggle("is-sorted", sorted);
            th.setAttribute("aria-sort", sorted ? (grid.sort.dir === "asc" ? "ascending" : "descending") : "none");
        });
        grid.onChange(visible, grid.rows.length, Object.keys(grid.filters).length > 0);
    };

    FilterGrid.prototype.clear = function () {
        this.filters = {};
        this.apply();
    };

    FilterGrid.prototype.openMenu = function (col, button) {
        var grid = this, kind = grid.kind(col);
        if (openState) { openState.button.setAttribute("aria-expanded", "false"); }
        openState = { grid: grid, col: col, button: button };
        button.setAttribute("aria-expanded", "true");
        menu.innerHTML = "";

        function addButton(label, cls, parent, onClick) {
            var b = document.createElement("button");
            b.type = "button";
            b.className = cls;
            b.textContent = label;
            b.addEventListener("click", onClick);
            parent.appendChild(b);
            return b;
        }
        var labels = kind === "money" ? ["Smallest → largest", "Largest → smallest"]
            : kind === "date" ? ["Oldest → newest", "Newest → oldest"] : ["A → Z", "Z → A"];
        addButton("Sort " + labels[0], "col-menu-item", menu, function () { grid.sort = { col: col, dir: "asc" }; grid.apply(); closeMenu(true); });
        addButton("Sort " + labels[1], "col-menu-item", menu, function () { grid.sort = { col: col, dir: "desc" }; grid.apply(); closeMenu(true); });

        if (kind !== "money") {
            // values in this column, counted over rows that pass the OTHER columns' filters
            var counts = {};
            grid.rows.forEach(function (row) {
                if (grid.passes(row, col)) {
                    var key = grid.rowKey(row, col);
                    counts[key] = (counts[key] || 0) + 1;
                }
            });
            var keys = Object.keys(counts).sort(function (a, b) {
                if (a === BLANK) { return 1; }
                if (b === BLANK) { return -1; }
                return kind === "date" ? b.localeCompare(a)
                    : a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
            });
            var current = grid.filters[col];
            menu.appendChild(document.createElement("hr"));

            var finder = null;
            if (keys.length > 8) {
                finder = document.createElement("input");
                finder.type = "search";
                finder.className = "col-menu-search";
                finder.placeholder = "Find a value…";
                finder.setAttribute("aria-label", "Find a value");
                menu.appendChild(finder);
            }
            var bulk = document.createElement("div");
            bulk.className = "col-menu-bulk";
            menu.appendChild(bulk);
            var list = document.createElement("div");
            list.className = "col-menu-list";
            menu.appendChild(list);

            var boxes = keys.map(function (key) {
                var label = document.createElement("label");
                label.className = "col-menu-option";
                var box = document.createElement("input");
                box.type = "checkbox";
                box.value = key;
                box.checked = !current || current.has(key);
                var text = document.createElement("span");
                text.textContent = keyLabel(kind, key);
                var count = document.createElement("span");
                count.className = "col-menu-count";
                count.textContent = counts[key];
                label.appendChild(box);
                label.appendChild(text);
                label.appendChild(count);
                list.appendChild(label);
                return box;
            });

            function commit() {
                var chosen = boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
                if (chosen.length === boxes.length) { delete grid.filters[col]; }
                else { grid.filters[col] = new Set(chosen); }
                grid.apply();
            }
            function setVisible(checked) {
                boxes.forEach(function (b) { if (!b.parentNode.hidden) { b.checked = checked; } });
                commit();
            }
            addButton("Select all", "link-btn", bulk, function () { setVisible(true); });
            addButton("Clear", "link-btn", bulk, function () { setVisible(false); });
            list.addEventListener("change", commit);
            if (finder) {
                finder.addEventListener("input", function () {
                    var q = finder.value.trim().toLowerCase();
                    boxes.forEach(function (b) {
                        b.parentNode.hidden = !!q && b.parentNode.textContent.toLowerCase().indexOf(q) === -1;
                    });
                });
            }
        }

        // place under the heading, kept inside the window
        menu.hidden = false;
        var rect = button.getBoundingClientRect();
        var maxLeft = window.scrollX + document.documentElement.clientWidth - menu.offsetWidth - 12;
        menu.style.left = Math.max(window.scrollX + 12, Math.min(rect.left + window.scrollX, maxLeft)) + "px";
        menu.style.top = (rect.bottom + window.scrollY + 6) + "px";
        var first = menu.querySelector("input, button");
        if (first) { first.focus(); }
    };

    if (table) {
        var ledgerGrid = new FilterGrid(table, function (visible, totalRows, filtered) {
            var total = visible.reduce(function (sum, row) { return sum + (parseFloat(row.dataset.amount) || 0); }, 0);
            $("stat-count").textContent = visible.length;
            $("stat-total").textContent = peso.format(total);
            var showing = $("ledger-showing");
            showing.hidden = !filtered;
            showing.textContent = "Showing " + visible.length + " of " + totalRows;
            $("clear-filters").hidden = !filtered;
            $("no-results").hidden = !(filtered && visible.length === 0);
        });
        document.querySelectorAll("#clear-filters, [data-clear-filters]").forEach(function (button) {
            button.addEventListener("click", function () { ledgerGrid.clear(); });
        });
    }
    var duesTable = $("dues-table");
    if (duesTable) { new FilterGrid(duesTable); }
    window.KNYCFilterGrid = FilterGrid;     // reused by the audit log page

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
                    var label = headings[index] ? headings[index].textContent.replace("▾", "").trim() : "";
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
