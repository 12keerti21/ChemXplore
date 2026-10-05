// Sortable, filterable overview table with molecule selection for the comparison view.
(function () {
    const dataElement = document.getElementById("overview-data");
    const table = document.getElementById("overview-table");
    if (!dataElement || !table) {
        return;
    }

    const rows = JSON.parse(dataElement.textContent);
    const compareButton = document.getElementById("compare-button");
    const compareCount = document.getElementById("compare-count");
    const filterInput = document.getElementById("overview-filter");
    const hideRisky = document.getElementById("overview-hide-risky");
    const maxCompare = Number(compareButton.dataset.maxCompare);
    const selected = new Set();
    let sortKey = "number";
    let sortAscending = true;

    function fixed(digits) {
        return function (row, key) {
            return row[key].toFixed(digits);
        };
    }

    const columns = [
        {label: "", render: renderCheckbox},
        {label: "#", key: "number", render: renderNumber},
        {label: "SMILES", key: "smiles", render: renderSmiles},
        {label: "MW", key: "molecular_weight", format: fixed(1)},
        {label: "LogP", key: "logP", format: fixed(2)},
        {label: "QED", key: "QED", format: fixed(2), title: "Quantitative estimate of drug-likeness, 0 to 1"},
        {label: "SA", key: "sa_score", format: fixed(2), title: "Synthetic accessibility, 1 (easy) to 10 (hard)"},
        {label: "Rules", key: "rules_passed", format: (row) => row.rules_passed + "/" + row.num_rules, title: "Drug-likeness rules passed"},
        {label: "Alerts", key: "num_alerts", format: (row) => String(row.num_alerts), title: "PAINS and Brenk structural alerts"},
        {label: "Risk", key: "risk_score", render: renderRisk, title: "2 points per risk, 1 per caution"},
        {label: "Closest approved drug", key: "closest_drug", sortValue: (row) => row.closest_drug ? row.closest_drug.name : "", render: renderClosest},
    ];

    function cell(content) {
        const td = document.createElement("td");
        if (typeof content === "string") {
            td.textContent = content;
        } else if (content) {
            td.appendChild(content);
        }
        return td;
    }

    function renderCheckbox(row) {
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "form-check-input";
        checkbox.checked = selected.has(row.number);
        checkbox.setAttribute("aria-label", "Select molecule " + row.number + " to compare");
        checkbox.addEventListener("change", function () {
            if (checkbox.checked) {
                selected.add(row.number);
            } else {
                selected.delete(row.number);
            }
            updateCompareButton();
        });
        return cell(checkbox);
    }

    function renderNumber(row) {
        const link = document.createElement("a");
        link.href = "#molecule-" + row.number;
        link.textContent = String(row.number);
        return cell(link);
    }

    function renderSmiles(row) {
        const td = cell(row.smiles);
        td.className = "cx-mono text-break";
        td.style.maxWidth = "260px";
        return td;
    }

    function renderRisk(row) {
        const wrapper = document.createElement("div");
        wrapper.className = "cx-risk-badges";
        row.risk_flags.forEach(function (flag) {
            const badge = document.createElement("span");
            badge.className = "cx-badge cx-" + flag.level;
            badge.textContent = flag.key;
            badge.title = flag.label + ": " + flag.value;
            wrapper.appendChild(badge);
        });
        return cell(wrapper);
    }

    function renderClosest(row) {
        if (!row.closest_drug) {
            return cell("-");
        }
        const wrapper = document.createElement("span");
        const link = document.createElement("a");
        link.href = row.closest_drug.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = row.closest_drug.name;
        const similarity = document.createElement("span");
        similarity.className = "cx-muted";
        similarity.textContent = " (" + row.closest_drug.similarity.toFixed(2) + ")";
        wrapper.append(link, similarity);
        return cell(wrapper);
    }

    function sortValue(row, column) {
        return column.sortValue ? column.sortValue(row) : row[column.key];
    }

    function renderHeader() {
        const headerRow = table.querySelector("thead tr");
        headerRow.replaceChildren();
        columns.forEach(function (column) {
            const th = document.createElement("th");
            th.textContent = column.label;
            if (column.title) {
                th.title = column.title;
            }
            if (column.key) {
                th.classList.add("cx-sortable");
                if (column.key === sortKey) {
                    th.classList.add(sortAscending ? "cx-sorted-asc" : "cx-sorted-desc");
                }
                th.addEventListener("click", function () {
                    sortAscending = column.key === sortKey ? !sortAscending : true;
                    sortKey = column.key;
                    render();
                });
            }
            headerRow.appendChild(th);
        });
    }

    function visibleRows() {
        const query = filterInput.value.trim().toLowerCase();
        const column = columns.find((c) => c.key === sortKey);

        return rows
            .filter(function (row) {
                if (hideRisky.checked && row.high_risks > 0) {
                    return false;
                }
                const drugName = row.closest_drug ? row.closest_drug.name.toLowerCase() : "";
                return !query || row.smiles.toLowerCase().includes(query) || drugName.includes(query);
            })
            .sort(function (a, b) {
                const x = sortValue(a, column);
                const y = sortValue(b, column);
                const order = typeof x === "string" ? x.localeCompare(y) : x - y;
                return sortAscending ? order : -order;
            });
    }

    function render() {
        renderHeader();
        const body = table.querySelector("tbody");
        body.replaceChildren();
        visibleRows().forEach(function (row) {
            const tr = document.createElement("tr");
            columns.forEach(function (column) {
                if (column.render) {
                    tr.appendChild(column.render(row));
                } else {
                    const td = cell(column.format(row, column.key));
                    td.className = "cx-mono";
                    tr.appendChild(td);
                }
            });
            body.appendChild(tr);
        });
    }

    function updateCompareButton() {
        compareCount.textContent = String(selected.size);
        compareButton.disabled = selected.size < 2 || selected.size > maxCompare;
        compareButton.title = selected.size > maxCompare ? "Pick at most " + maxCompare + " molecules" : "";
    }

    compareButton.addEventListener("click", function () {
        const ids = Array.from(selected).sort((a, b) => a - b).join(",");
        window.open(compareButton.dataset.compareUrl + "?ids=" + ids, "_blank", "noopener");
    });
    filterInput.addEventListener("input", render);
    hideRisky.addEventListener("change", render);

    render();
    updateCompareButton();
})();
