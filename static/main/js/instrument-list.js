(() => {
    const rows = Array.from(document.querySelectorAll(".oil-instrument-row"));
    const detailRows = Array.from(
        document.querySelectorAll(".oil-instrument-detail-row"),
    );
    const allRows = [...rows, ...detailRows];
    const editButton = document.querySelector("#instrument-edit-button");
    const deleteButton = document.querySelector("#instrument-delete-button");
    const deleteForm = document.querySelector("#instrument-delete-form");
    let selectedRow = null;

    const selectRow = (row) => {
        allRows.forEach((candidate) => {
            candidate.classList.toggle("table-active", candidate === row);
            candidate.setAttribute(
                "aria-selected",
                candidate === row ? "true" : "false",
            );
        });
        selectedRow = row;
    };

    rows.forEach((row) => {
        row.addEventListener("click", (event) => {
            if (event.target.closest("a, button, form")) {
                return;
            }
            selectRow(row);
        });
        row.addEventListener("dblclick", (event) => {
            if (event.target.closest("a, button, form")) {
                return;
            }
            window.location.assign(row.dataset.detailUrl);
        });
    });

    detailRows.forEach((row) => {
        row.addEventListener("click", () => selectRow(row));
        row.addEventListener("dblclick", (event) => {
            if (event.target.closest("a, button, form")) {
                return;
            }
            window.location.assign(row.dataset.detailUrl);
        });
    });

    const selectFirstRow = () => {
        if (allRows.length) {
            selectRow(allRows[0]);
        }
    };
    window.addEventListener("pageshow", selectFirstRow);
    selectFirstRow();

    editButton?.addEventListener("click", () => {
        if (!selectedRow) {
            window.alert("Select an instrument first.");
            return;
        }
        window.location.assign(selectedRow.dataset.editUrl);
    });

    deleteButton?.addEventListener("click", () => {
        if (!selectedRow) {
            window.alert("Select an instrument first.");
            return;
        }
        if (!deleteForm) {
            return;
        }
        const instrumentName = selectedRow.dataset.instrumentName;
        if (window.confirm(`Delete instrument "${instrumentName}"?`)) {
            deleteForm.action = selectedRow.dataset.deleteUrl;
            deleteForm.submit();
        }
    });
})();
