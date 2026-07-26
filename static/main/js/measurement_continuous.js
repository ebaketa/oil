const continuousForm = document.querySelector("#measurement-continuous-form");

if (continuousForm) {
    const startButton = document.querySelector("#measurement-continuous-start");
    const stopButton = document.querySelector("#measurement-continuous-stop");
    const settings = document.querySelector("#measurement-continuous-settings");
    const resultsBody = document.querySelector("#measurement-continuous-results");
    const messageContainer = document.querySelector(
        "#measurement-continuous-message",
    );
    const summary = document.querySelector("#measurement-continuous-summary");
    let activeSessionId = null;
    let stopping = false;

    const createSessionId = () => {
        if (typeof crypto.randomUUID === "function") {
            return crypto.randomUUID();
        }

        const bytes = new Uint8Array(16);
        crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        const hex = Array.from(
            bytes,
            (value) => value.toString(16).padStart(2, "0"),
        );
        return [
            hex.slice(0, 4).join(""),
            hex.slice(4, 6).join(""),
            hex.slice(6, 8).join(""),
            hex.slice(8, 10).join(""),
            hex.slice(10, 16).join(""),
        ].join("-");
    };

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
    };

    const setFieldsDisabled = (disabled) => {
        for (const element of continuousForm.elements) {
            if (!["csrfmiddlewaretoken"].includes(element.name)
                    && element !== stopButton) {
                element.disabled = disabled;
            }
        }
        stopButton.disabled = false;
    };

    const addResult = (result) => {
        document.querySelector("#measurement-continuous-empty")?.remove();
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

    const requestStop = async () => {
        if (!activeSessionId || stopping) {
            return;
        }
        stopping = true;
        stopButton.disabled = true;
        stopButton.textContent = "Stopping…";
        const data = new FormData();
        data.append(
            "csrfmiddlewaretoken",
            continuousForm.elements.csrfmiddlewaretoken.value,
        );
        data.append("session_id", activeSessionId);

        const response = await fetch(continuousForm.dataset.stopUrl, {
            method: "POST",
            body: data,
            headers: {"X-Requested-With": "XMLHttpRequest"},
        });
        if (!response.ok && response.status !== 404) {
            const payload = await response.json();
            stopping = false;
            stopButton.disabled = false;
            stopButton.textContent = "Stop";
            throw new Error(payload.error || "The measurement could not stop.");
        }
    };

    stopButton.addEventListener("click", async () => {
        try {
            await requestStop();
        } catch (error) {
            showMessage(error.message, "danger");
        }
    });

    continuousForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        activeSessionId = createSessionId();
        stopping = false;

        const instrument = continuousForm.elements.instrument;
        const measurement = continuousForm.elements.measurement_type;
        document.querySelector("#continuous-summary-instrument").textContent =
            instrument.options[instrument.selectedIndex].text;
        document.querySelector("#continuous-summary-measurement").textContent =
            measurement.options[measurement.selectedIndex].text;
        document.querySelector("#continuous-summary-interval").textContent =
            continuousForm.elements.interval_seconds.value;
        document.querySelector("#continuous-summary-notes").textContent =
            continuousForm.elements.notes.value.trim() || "—";

        const data = new FormData(continuousForm);
        data.append("session_id", activeSessionId);
        resultsBody.replaceChildren();
        messageContainer.replaceChildren();
        summary.classList.remove("d-none");
        settings.classList.add("d-none");
        startButton.classList.add("d-none");
        startButton.textContent = "Measuring…";
        stopButton.classList.remove("d-none");
        setFieldsDisabled(true);
        let resultCount = 0;
        let streamAccepted = false;

        try {
            const response = await fetch(continuousForm.dataset.streamUrl, {
                method: "POST",
                body: data,
                headers: {"X-Requested-With": "XMLHttpRequest"},
            });
            if (!response.ok) {
                const payload = await response.json();
                const errors = Object.values(payload.errors || {})
                    .flat()
                    .map((error) => error.message)
                    .join(" ");
                throw new Error(
                    errors || payload.error
                    || "Continuous measurement could not start.",
                );
            }
            streamAccepted = true;
            if (!response.body) {
                throw new Error("Live result streaming is not supported.");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const {value, done} = await reader.read();
                buffer += decoder.decode(
                    value || new Uint8Array(),
                    {stream: !done},
                );
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
                settings.classList.remove("d-none");
                summary.classList.add("d-none");
            }
            showMessage(
                `Continuous measurement failed: ${error.message}`,
                "danger",
            );
        } finally {
            activeSessionId = null;
            stopping = false;
            setFieldsDisabled(false);
            startButton.textContent = "Start";
            startButton.classList.remove("d-none");
            stopButton.textContent = "Stop";
            stopButton.classList.add("d-none");
        }
    });

    window.addEventListener("beforeunload", () => {
        if (!activeSessionId) {
            return;
        }
        const data = new FormData();
        data.append(
            "csrfmiddlewaretoken",
            continuousForm.elements.csrfmiddlewaretoken.value,
        );
        data.append("session_id", activeSessionId);
        navigator.sendBeacon(continuousForm.dataset.stopUrl, data);
    });
}
