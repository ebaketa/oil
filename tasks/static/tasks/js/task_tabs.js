(() => {
    "use strict";

    const newButton = document.querySelector("#task-new-button");
    const openButton = document.querySelector("#task-open-button");
    const tabList = document.querySelector("#task-tabs");
    const tabContent = document.querySelector("#task-tab-content");
    const tabTemplate = document.querySelector("#task-tab-template");
    const newPaneTemplate = document.querySelector("#task-pane-template");
    const savedPaneTemplate = document.querySelector(
        "#saved-task-pane-template",
    );
    const statusFilter = document.querySelector("#task-status-filter");
    const taskRows = Array.from(document.querySelectorAll(".task-row"));
    const availableInstrumentData = document.querySelector(
        "#task-available-instruments",
    );
    const availableInstruments = availableInstrumentData
        ? JSON.parse(availableInstrumentData.textContent)
        : [];
    const instrumentsById = new Map(
        availableInstruments.map((instrument) => [
            String(instrument.id),
            instrument,
        ]),
    );

    if (
        !newButton
        || !openButton
        || !tabList
        || !tabContent
        || !tabTemplate
        || !newPaneTemplate
        || !savedPaneTemplate
    ) {
        return;
    }

    let nextNewTaskNumber = 1;
    let selectedRow = null;

    const formatDateTime = (value) => {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        const pad = (part) => String(part).padStart(2, "0");
        return (
            `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.`
            + `${date.getFullYear()} ${pad(date.getHours())}:`
            + `${pad(date.getMinutes())}:${pad(date.getSeconds())}`
        );
    };

    const activateTab = (trigger) => {
        bootstrap.Tab.getOrCreateInstance(trigger).show();
    };

    const activateNearestTab = (closedTab) => {
        const replacement = closedTab.nextElementSibling
            || closedTab.previousElementSibling;
        if (replacement) {
            activateTab(replacement.querySelector('[role="tab"]'));
        }
    };

    const closeTab = (tabItem, pane, trigger) => {
        if (pane.taskPollTimer) {
            window.clearInterval(pane.taskPollTimer);
        }
        if (trigger.classList.contains("active")) {
            activateNearestTab(tabItem);
        }
        bootstrap.Tab.getOrCreateInstance(trigger).dispose();
        tabItem.remove();
        pane.remove();
    };

    const createTab = ({ tabId, paneId, title, pane }) => {
        const tabItem = tabTemplate.content.firstElementChild.cloneNode(true);
        const trigger = tabItem.querySelector('[role="tab"]');
        const closeButton = tabItem.querySelector(".task-tab-close");

        trigger.id = tabId;
        trigger.querySelector(".task-tab-label").textContent = title;
        trigger.dataset.bsToggle = "tab";
        trigger.dataset.bsTarget = `#${paneId}`;
        trigger.setAttribute("aria-controls", paneId);
        trigger.setAttribute("aria-selected", "false");

        pane.id = paneId;
        pane.setAttribute("aria-labelledby", tabId);

        closeButton.addEventListener("click", (event) => {
            event.stopPropagation();
            closeTab(tabItem, pane, trigger);
        });
        closeButton.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                event.stopPropagation();
                closeTab(tabItem, pane, trigger);
            }
        });

        tabList.append(tabItem);
        tabContent.append(pane);
        activateTab(trigger);
        return trigger;
    };

    const addField = (container, label, name, value, options = null) => {
        const wrapper = document.createElement("div");
        wrapper.className = "col-md-6";
        const labelElement = document.createElement("label");
        labelElement.className = "form-label";
        labelElement.textContent = label;
        let control;
        if (options) {
            control = document.createElement("select");
            control.className = "form-select";
            options.forEach(([optionValue, optionLabel]) => {
                const option = document.createElement("option");
                option.value = optionValue;
                option.textContent = optionLabel;
                option.selected = String(optionValue) === String(value);
                control.append(option);
            });
        } else {
            control = document.createElement("input");
            control.className = "form-control";
            control.type = "number";
            control.step = "0.001";
            control.value = value;
        }
        control.dataset.configName = name;
        wrapper.append(labelElement, control);
        container.append(wrapper);
        return control;
    };

    const buildInstrumentConfiguration = (instrument, panel) => {
        const heading = document.createElement("div");
        heading.className = "mb-3";
        const title = document.createElement("h4");
        title.className = "h6 mb-1";
        title.textContent = instrument.name;
        const driver = document.createElement("div");
        driver.className = "small text-muted";
        driver.textContent = instrument.driver_label;
        heading.append(title, driver);
        panel.append(heading);

        const fields = document.createElement("div");
        fields.className = "row g-3";
        panel.append(fields);

        if (instrument.driver === "mock_dc_power_supply") {
            addField(fields, "Mode", "mode", "sweep", [
                ["fixed", "Fixed"],
                ["sweep", "Sweep"],
                ["cycle", "Cycle"],
            ]);
            addField(fields, "Start voltage (V)", "start_voltage", "0.000");
            addField(fields, "Stop voltage (V)", "stop_voltage", "10.000");
            addField(fields, "Voltage step (V)", "voltage_step", "1.000");
            const cycles = addField(
                fields,
                "Cycle count",
                "cycle_count",
                "1",
            );
            cycles.step = "1";
            cycles.min = "1";
            cycles.max = "100";
            return;
        }

        if (Object.keys(instrument.capabilities).length) {
            const capabilityOptions = Object.entries(
                instrument.capabilities,
            ).map(([name, capability]) => [name, capability.label]);
            const functionField = addField(
                fields,
                "Function",
                "function",
                capabilityOptions[0]?.[0] || "",
                capabilityOptions,
            );
            const sourceOptions = [["external", "External"]];
            if (instrument.driver === "mock") {
                sourceOptions.push(["virtual", "Virtual power supply"]);
            }
            addField(
                fields,
                "Source",
                "source",
                "external",
                sourceOptions,
            );
            const minimum = addField(
                fields,
                "Minimum temperature (°C)",
                "minimum",
                "20.00",
            );
            const maximum = addField(
                fields,
                "Maximum temperature (°C)",
                "maximum",
                "30.00",
            );
            const resolution = addField(
                fields,
                "Temperature resolution (°C)",
                "resolution",
                "0.10",
            );
            const seed = addField(fields, "Random seed", "seed", "1");
            seed.step = "1";

            const updateTemperatureFields = () => {
                const visible = functionField.value === "temperature";
                [minimum, maximum, resolution, seed].forEach((field) => {
                    field.closest(".col-md-6").classList.toggle(
                        "d-none",
                        !visible,
                    );
                });
            };
            functionField.addEventListener("change", updateTemperatureFields);
            updateTemperatureFields();
        }
    };

    const initializeInstrumentBuilder = (pane) => {
        const select = pane.querySelector(".task-instrument-select");
        const addButton = pane.querySelector(".task-add-instrument");
        const tabs = pane.querySelector(".task-instrument-tabs");
        const content = pane.querySelector(".task-instrument-content");
        const emptyMessage = pane.querySelector(".task-no-instruments");
        const added = new Map();

        const activateNested = (trigger) => {
            bootstrap.Tab.getOrCreateInstance(trigger).show();
        };

        const removeInstrument = (instrumentId) => {
            const entry = added.get(instrumentId);
            if (!entry) {
                return;
            }
            const wasActive = entry.trigger.classList.contains("active");
            const replacement = entry.tab.nextElementSibling
                || entry.tab.previousElementSibling;
            entry.tab.remove();
            entry.panel.remove();
            added.delete(instrumentId);
            const option = select.querySelector(
                `option[value="${instrumentId}"]`,
            );
            if (option) {
                option.disabled = false;
            }
            if (wasActive && replacement) {
                activateNested(replacement.querySelector('[role="tab"]'));
            }
            emptyMessage.classList.toggle("d-none", added.size > 0);
        };

        addButton.addEventListener("click", () => {
            const instrumentId = select.value;
            const instrument = instrumentsById.get(instrumentId);
            if (!instrument || added.has(instrumentId)) {
                return;
            }

            const tab = document.createElement("li");
            tab.className = "nav-item";
            tab.role = "presentation";
            const trigger = document.createElement("button");
            trigger.className = "nav-link d-flex align-items-center gap-2";
            trigger.type = "button";
            trigger.role = "tab";
            const triggerLabel = document.createElement("span");
            triggerLabel.textContent = instrument.name;
            trigger.dataset.bsToggle = "tab";
            const panelId = (
                `${pane.id}-instrument-${instrumentId}`
            );
            trigger.dataset.bsTarget = `#${panelId}`;
            const remove = document.createElement("span");
            remove.role = "button";
            remove.tabIndex = 0;
            remove.textContent = "×";
            remove.setAttribute("aria-label", "Remove instrument");
            trigger.append(triggerLabel, remove);
            tab.append(trigger);

            const panel = document.createElement("section");
            panel.className = "tab-pane fade";
            panel.id = panelId;
            panel.role = "tabpanel";
            panel.dataset.instrumentId = instrumentId;
            buildInstrumentConfiguration(instrument, panel);

            tabs.append(tab);
            content.append(panel);
            added.set(instrumentId, {instrument, tab, trigger, panel});
            select.querySelector(
                `option[value="${instrumentId}"]`,
            ).disabled = true;
            select.value = "";
            emptyMessage.classList.add("d-none");
            remove.addEventListener("click", (event) => {
                event.stopPropagation();
                removeInstrument(instrumentId);
            });
            remove.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    event.stopPropagation();
                    removeInstrument(instrumentId);
                }
            });
            activateNested(trigger);
        });

        return () => Array.from(added.values()).map((entry) => {
            const configuration = {};
            entry.panel.querySelectorAll("[data-config-name]").forEach(
                (field) => {
                    configuration[field.dataset.configName] = field.value;
                },
            );
            return {
                instrument_id: entry.instrument.id,
                configuration,
            };
        });
    };

    const openNewTask = () => {
        const number = nextNewTaskNumber;
        nextNewTaskNumber += 1;
        const pane = newPaneTemplate.content.firstElementChild.cloneNode(true);
        const trigger = createTab({
            tabId: `new-task-tab-${number}`,
            paneId: `new-task-pane-${number}`,
            title: `New Task ${number}`,
            pane,
        });
        const form = pane.querySelector(".task-create-form");
        const collectInstruments = initializeInstrumentBuilder(pane);
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const submitButton = form.querySelector('[type="submit"]');
            const errorBox = form.querySelector(".task-form-error");
            submitButton.disabled = true;
            errorBox.classList.add("d-none");
            form.querySelectorAll(".is-invalid").forEach((field) => {
                field.classList.remove("is-invalid");
            });

            try {
                form.querySelector(".task-instruments-payload").value = (
                    JSON.stringify(collectInstruments())
                );
                const response = await fetch(form.action, {
                    method: "POST",
                    body: new FormData(form),
                    headers: {"X-Requested-With": "XMLHttpRequest"},
                });
                const payload = await response.json();
                if (!response.ok) {
                    if (payload.errors) {
                        Object.entries(payload.errors).forEach(
                            ([name, errors]) => {
                                const field = form.elements.namedItem(name);
                                if (field) {
                                    field.classList.add("is-invalid");
                                    field.parentElement.querySelector(
                                        ".invalid-feedback",
                                    ).textContent = errors[0].message;
                                }
                            },
                        );
                    }
                    throw new Error(
                        payload.error || "Task settings are invalid.",
                    );
                }
                trigger.closest("li").querySelector(
                    ".task-tab-close",
                ).click();
                openTaskData(payload);
            } catch (error) {
                errorBox.textContent = error.message;
                errorBox.classList.remove("d-none");
            } finally {
                submitButton.disabled = false;
            }
        });
    };

    const selectRow = (row) => {
        if (selectedRow) {
            selectedRow.classList.remove("table-active");
            selectedRow.setAttribute("aria-selected", "false");
        }
        selectedRow = row;
        selectedRow.classList.add("table-active");
        selectedRow.setAttribute("aria-selected", "true");
        openButton.disabled = false;
    };

    const renderTaskData = (pane, task) => {
        pane.querySelector(".saved-task-heading").textContent = task.name;
        pane.querySelector(".saved-task-summary").textContent = (
            `${task.voltage_mode} · ${task.voltage_source}`
        );
        const status = pane.querySelector(".saved-task-status");
        status.textContent = task.status_label;
        status.classList.remove(
            "btn-primary",
            "btn-success",
            "btn-secondary",
            "btn-danger",
        );
        status.classList.add({
            pending: "btn-primary",
            running: "btn-primary",
            completed: "btn-success",
            stopped: "btn-secondary",
            failed: "btn-danger",
        }[task.status] || "btn-secondary");
        const exportButton = pane.querySelector(".task-export-button");
        exportButton.classList.toggle(
            "d-none",
            task.status !== "completed",
        );
        exportButton.href = `/tasks/${task.id}/export.csv`;
        pane.querySelector(".saved-task-started").textContent = (
            formatDateTime(task.started_at)
        );
        pane.querySelector(".saved-task-count").textContent = (
            task.sample_count
        );
        pane.querySelector(".task-detail-error").textContent = task.error || "";
        const stopButton = pane.querySelector(".task-stop-button");
        stopButton.classList.toggle(
            "d-none",
            !["pending", "running"].includes(task.status),
        );

        const rows = pane.querySelector(".task-sample-rows");
        const header = pane.querySelector(".task-results-header");
        header.replaceChildren();
        const timeHeader = document.createElement("th");
        timeHeader.textContent = "Time";
        header.append(timeHeader);
        const instruments = task.instruments || [];
        instruments.forEach((instrument) => {
            const cell = document.createElement("th");
            cell.textContent = instrument.name;
            cell.title = instrument.driver;
            header.append(cell);
        });

        rows.replaceChildren();
        [...(task.samples || [])].reverse().forEach((sample) => {
            const row = document.createElement("tr");
            const timeCell = document.createElement("td");
            timeCell.textContent = formatDateTime(sample.timestamp);
            row.append(timeCell);
            const readingsByInstrument = new Map(
                (sample.readings || []).map((reading) => [
                    String(reading.assignment_id),
                    reading,
                ]),
            );
            instruments.forEach((instrument) => {
                const cell = document.createElement("td");
                const reading = readingsByInstrument.get(
                    String(instrument.assignment_id),
                );
                if (reading) {
                    cell.textContent = `${reading.value} ${reading.unit}`;
                    cell.title = reading.parameter;
                } else {
                    cell.textContent = "—";
                }
                row.append(cell);
            });
            rows.append(row);
        });
    };

    const fetchTask = async (taskId, pane) => {
        const response = await fetch(`/tasks/${taskId}/`);
        if (!response.ok) {
            throw new Error("Task data could not be loaded.");
        }
        const task = await response.json();
        renderTaskData(pane, task);
        if (!["pending", "running"].includes(task.status) && pane.taskPollTimer) {
            window.clearInterval(pane.taskPollTimer);
            pane.taskPollTimer = null;
        }
    };

    const startPolling = (taskId, pane) => {
        fetchTask(taskId, pane).catch((error) => {
            pane.querySelector(".task-detail-error").textContent = error.message;
        });
        pane.taskPollTimer = window.setInterval(() => {
            fetchTask(taskId, pane).catch((error) => {
                pane.querySelector(".task-detail-error").textContent = (
                    error.message
                );
            });
        }, 1000);
    };

    const openTaskData = (task) => {
        const taskId = String(task.id);
        const existingTrigger = document.querySelector(
            `[data-open-task-id="${taskId}"]`,
        );
        if (existingTrigger) {
            activateTab(existingTrigger);
            return;
        }
        const pane = (
            savedPaneTemplate.content.firstElementChild.cloneNode(true)
        );
        renderTaskData(pane, task);
        const trigger = createTab({
            tabId: `saved-task-tab-${taskId}`,
            paneId: `saved-task-pane-${taskId}`,
            title: task.name,
            pane,
        });
        trigger.dataset.openTaskId = taskId;
        pane.querySelector(".task-stop-button").addEventListener(
            "click",
            async () => {
                const csrfToken = document.querySelector(
                    '[name="csrfmiddlewaretoken"]',
                ).value;
                const response = await fetch(`/tasks/${taskId}/stop/`, {
                    method: "POST",
                    headers: {"X-CSRFToken": csrfToken},
                });
                if (!response.ok) {
                    const payload = await response.json();
                    pane.querySelector(".task-detail-error").textContent = (
                        payload.error || "Task could not be stopped."
                    );
                }
            },
        );
        startPolling(taskId, pane);
    };

    const openSavedTask = (row) => {
        if (!row) {
            return;
        }
        const taskId = row.dataset.taskId;
        const existingTrigger = document.querySelector(
            `[data-open-task-id="${taskId}"]`,
        );
        if (existingTrigger) {
            activateTab(existingTrigger);
            return;
        }

        fetch(`/tasks/${taskId}/`)
            .then((response) => {
                if (!response.ok) {
                    throw new Error("Task data could not be loaded.");
                }
                return response.json();
            })
            .then(openTaskData);
    };

    const filterRows = () => {
        if (!statusFilter) {
            return;
        }
        const status = statusFilter.value;
        taskRows.forEach((row) => {
            row.classList.toggle(
                "d-none",
                Boolean(status) && row.dataset.status !== status,
            );
        });
        if (
            selectedRow
            && selectedRow.classList.contains("d-none")
        ) {
            selectedRow.classList.remove("table-active");
            selectedRow.setAttribute("aria-selected", "false");
            selectedRow = null;
            openButton.disabled = true;
        }
    };

    taskRows.forEach((row) => {
        row.addEventListener("click", () => selectRow(row));
        row.addEventListener("dblclick", () => openSavedTask(row));
        row.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectRow(row);
                if (event.key === "Enter") {
                    openSavedTask(row);
                }
            }
        });
    });

    newButton.addEventListener("click", openNewTask);
    openButton.addEventListener("click", () => openSavedTask(selectedRow));
    statusFilter?.addEventListener("change", filterRows);

    taskRows
        .filter((row) => ["pending", "running"].includes(row.dataset.status))
        .forEach((row) => openSavedTask(row));
})();
