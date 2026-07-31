(() => {
    const rows = Array.from(document.querySelectorAll(".measurement-row"));

    const selectRow = (row) => {
        rows.forEach((candidate) => {
            candidate.classList.toggle("table-active", candidate === row);
            candidate.setAttribute(
                "aria-selected",
                candidate === row ? "true" : "false",
            );
        });
    };

    rows.forEach((row) => {
        row.addEventListener("click", () => selectRow(row));
        row.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectRow(row);
            }
        });
    });

    if (rows.length) {
        selectRow(rows[0]);
    }
})();
