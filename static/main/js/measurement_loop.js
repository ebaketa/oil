const loopForm = document.querySelector("#measurement-loop-form");

if (loopForm) {
    const startButton = document.querySelector("#measurement-loop-start");
    const resultsBody = document.querySelector("#measurement-loop-results");
    const messageContainer = document.querySelector("#measurement-loop-message");
    const summary = document.querySelector("#measurement-loop-summary");
    const summaryInstrument = document.querySelector("#loop-summary-instrument");
    const summaryMeasurement = document.querySelector("#loop-summary-measurement");
    const summaryCount = document.querySelector("#loop-summary-count");
    const summaryInterval = document.querySelector("#loop-summary-interval");
    const summaryNotes = document.querySelector("#loop-summary-notes");

    const showMessage = (text, type) => {
        messageContainer.replaceChildren();
        const message = document.createElement("div");
        message.className = `alert alert-${type} alert-dismissible fade show`;
        message.setAttribute("role", "alert");
        message.textContent = text;

        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "btn-close";
        closeButton.dataset.bsDismiss = "alert";
        closeButton.setAttribute("aria-label", "Close");
        message.append(closeButton);
        messageContainer.append(message);

        if (type === "success") {
            window.setTimeout(() => {
                bootstrap.Alert.getOrCreateInstance(message).close();
            }, 4000);
        }
    };

    const addResult = (result) => {
        document.querySelector("#measurement-loop-empty")?.remove();

        const row = document.createElement("tr");
        const values = [
            result.index,
            new Date(result.timestamp).toLocaleString(),
            result.instrument,
            result.parameter,
            result.value,
            result.unit,
        ];

        values.forEach((value, index) => {
            const cell = document.createElement("td");
            cell.textContent = value;
            if (index === 4) {
                cell.className = "text-end";
            }
            row.append(cell);
        });
        resultsBody.prepend(row);
        resultsBody.closest(".oil-measurement-table-scroll").scrollTop = 0;
    };

    loopForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const instrumentField = loopForm.elements.instrument;
        const measurementField = loopForm.elements.measurement_type;
        summaryInstrument.textContent =
            instrumentField.options[instrumentField.selectedIndex].text;
        summaryMeasurement.textContent =
            measurementField.options[measurementField.selectedIndex].text;
        summaryCount.textContent = loopForm.elements.count.value;
        summaryInterval.textContent = loopForm.elements.interval_seconds.value;
        summaryNotes.textContent = loopForm.elements.notes.value.trim() || "—";
        summary.classList.remove("d-none");
        loopForm.classList.add("d-none");
        startButton.classList.add("d-none");

        startButton.disabled = true;
        startButton.textContent = "Measuring…";
        resultsBody.replaceChildren();
        messageContainer.replaceChildren();
        let streamAccepted = false;

        try {
            const response = await fetch(loopForm.dataset.streamUrl, {
                method: "POST",
                body: new FormData(loopForm),
                headers: {"X-Requested-With": "XMLHttpRequest"},
            });

            if (!response.ok) {
                const payload = await response.json();
                const errors = Object.values(payload.errors || {})
                    .flat()
                    .map((error) => error.message)
                    .join(" ");
                throw new Error(errors || "The measurement loop could not start.");
            }
            streamAccepted = true;
            if (!response.body) {
                throw new Error("Live result streaming is not supported.");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let resultCount = 0;

            while (true) {
                const {value, done} = await reader.read();
                buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
                const lines = buffer.split("\n");
                buffer = lines.pop() || "";

                for (const line of lines) {
                    if (!line.trim()) {
                        continue;
                    }
                    const result = JSON.parse(line);
                    if (result.error) {
                        throw new Error(result.error);
                    }
                    addResult(result);
                    resultCount += 1;
                }
                if (done) {
                    break;
                }
            }

            showMessage(`${resultCount} measurements recorded.`, "success");
        } catch (error) {
            if (!streamAccepted) {
                loopForm.classList.remove("d-none");
                summary.classList.add("d-none");
                startButton.classList.remove("d-none");
            }
            showMessage(`Measurement loop failed: ${error.message}`, "danger");
        } finally {
            startButton.disabled = false;
            startButton.textContent = "Start";
        }
    });
}
