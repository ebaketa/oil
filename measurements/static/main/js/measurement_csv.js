// Export the measurement rows currently displayed by a workflow.
(() => {
    const numericValue = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

    const protectSpreadsheetCell = (value) => {
        const trimmed = value.trim();
        if (numericValue.test(trimmed)) {
            return value;
        }
        if (/^\s*[=+\-@]/.test(value) || /^[\t\r]/.test(value)) {
            return `'${value}`;
        }
        return value;
    };

    const csvCell = (value) => {
        const protectedValue = protectSpreadsheetCell(value);
        return `"${protectedValue.replace(/"/g, "\"\"")}"`;
    };

    const timestampForFilename = () => {
        const now = new Date();
        const date = [
            now.getFullYear(),
            String(now.getMonth() + 1).padStart(2, "0"),
            String(now.getDate()).padStart(2, "0"),
        ].join("");
        const time = [
            String(now.getHours()).padStart(2, "0"),
            String(now.getMinutes()).padStart(2, "0"),
            String(now.getSeconds()).padStart(2, "0"),
        ].join("");
        return `${date}-${time}`;
    };

    const resultRows = (table) => Array.from(
        table.querySelectorAll("tbody tr:not([data-csv-empty])"),
    );

    const bindExport = (button) => {
        const table = document.querySelector(`#${button.dataset.csvTarget}`);
        if (!table) {
            return;
        }

        const updateAvailability = () => {
            button.disabled = resultRows(table).length === 0;
        };

        button.addEventListener("click", () => {
            const rows = resultRows(table);
            if (!rows.length) {
                return;
            }

            const headers = Array.from(table.querySelectorAll("thead th"))
                .map((cell) => cell.textContent.trim());
            const csvRows = [
                headers,
                ...rows.map((row) => Array.from(row.cells)
                    .map((cell) => cell.textContent.trim())),
            ];
            const csv = csvRows
                .map((row) => row.map(csvCell).join(","))
                .join("\r\n");
            const blob = new Blob([`\uFEFF${csv}\r\n`], {
                type: "text/csv;charset=utf-8",
            });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = (
                `${button.dataset.csvFilename}-${timestampForFilename()}.csv`
            );
            document.body.append(link);
            link.click();
            link.remove();
            window.setTimeout(() => URL.revokeObjectURL(url), 0);
        });

        new MutationObserver(updateAvailability).observe(
            table.tBodies[0],
            {childList: true},
        );
        updateAvailability();
    };

    document.querySelectorAll("[data-csv-export]").forEach(bindExport);
})();
