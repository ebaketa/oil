// Measurements domain asset.
const singleForm = document.querySelector("#measurement-single-form");

if (singleForm) {
    const measureButton = document.querySelector("#measurement-single-repeat");
    const summary = document.querySelector("#measurement-single-summary");
    const resultsBody = document.querySelector("#measurement-single-results");
    const messageContainer = document.querySelector("#measurement-single-message");

    const showError = (text) => {
        messageContainer.replaceChildren();
        const message = document.createElement("div");
        message.className = "alert alert-danger";
        message.setAttribute("role", "alert");
        message.textContent = text;
        messageContainer.append(message);
    };

    const addResult = (result) => {
        document.querySelector("#measurement-single-empty")?.remove();
        const row = document.createElement("tr");
        const values = [
            new Date(result.timestamp).toLocaleString(),
            result.instrument,
            result.parameter,
            result.value,
            result.unit,
        ];
        values.forEach((value, index) => {
            const cell = document.createElement("td");
            cell.textContent = value;
            if (index === 3) {
                cell.className = "text-end";
            }
            row.append(cell);
        });
        resultsBody.prepend(row);
        resultsBody.closest(".oil-measurement-table-scroll").scrollTop = 0;
    };

    singleForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const instrument = singleForm.elements.instrument;
        const measurement = singleForm.elements.measurement_type;

        document.querySelector("#single-summary-instrument").textContent =
            instrument.options[instrument.selectedIndex].text;
        document.querySelector("#single-summary-measurement").textContent =
            measurement.options[measurement.selectedIndex].text;
        document.querySelector("#single-summary-notes").textContent =
            singleForm.elements.notes.value.trim() || "—";

        summary.classList.remove("d-none");
        singleForm.classList.add("d-none");
        measureButton.disabled = true;
        measureButton.textContent = "Measuring…";
        messageContainer.replaceChildren();

        try {
            const response = await fetch(singleForm.dataset.measureUrl, {
                method: "POST",
                body: new FormData(singleForm),
                headers: {"X-Requested-With": "XMLHttpRequest"},
            });
            const payload = await response.json();
            if (!response.ok) {
                const errors = Object.values(payload.errors || {})
                    .flat()
                    .map((error) => error.message)
                    .join(" ");
                throw new Error(
                    errors || payload.error || "Measurement failed.",
                );
            }
            addResult(payload);
        } catch (error) {
            showError(`Measurement failed: ${error.message}`);
        } finally {
            measureButton.disabled = false;
            measureButton.textContent = "Measure";
        }
    });
}
