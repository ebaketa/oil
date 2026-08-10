(() => {
    "use strict";

    const newButton = document.querySelector("#task-new-button");
    const openButton = document.querySelector("#task-open-button");
    const deleteButton = document.querySelector("#task-delete-button");
    const tabList = document.querySelector("#task-tabs");
    const tabContent = document.querySelector("#task-tab-content");
    const tabTemplate = document.querySelector("#task-tab-template");
    const newPaneTemplate = document.querySelector("#task-pane-template");
    const savedPaneTemplate = document.querySelector(
        "#saved-task-pane-template",
    );
    const statusFilter = document.querySelector("#task-status-filter");
    const savedTaskTable = document.querySelector("#saved-task-table");
    const taskRows = Array.from(document.querySelectorAll(".task-row"));
    const isAdmin = savedTaskTable?.dataset.isAdmin === "true";
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
        || !deleteButton
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

    const formatElapsed = (startedAt, finishedAt = null) => {
        if (!startedAt) {
            return "—";
        }
        const started = new Date(startedAt).getTime();
        const finished = finishedAt
            ? new Date(finishedAt).getTime()
            : Date.now();
        const totalSeconds = Math.max(
            0,
            Math.floor((finished - started) / 1000),
        );
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        const pad = (part) => String(part).padStart(2, "0");
        return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    };

    const chartColors = [
        "#0d6efd",
        "#dc3545",
        "#198754",
        "#fd7e14",
        "#6f42c1",
        "#0dcaf0",
    ];

    const renderLiveChart = (pane, task, resultColumns) => {
        const canvas = pane.querySelector(".task-live-chart");
        const legend = pane.querySelector(".task-chart-legend");
        const empty = pane.querySelector(".task-chart-empty");
        const samples = [...(task.samples || [])].filter(
            (sample) => sample.acquisition_time_seconds !== null
                || sample.status === "failed",
        ).sort(
            (left, right) => left.index - right.index,
        );
        const findReading = (sample, column) => (sample.readings || []).find(
            (candidate) => (
                String(candidate.assignment_id)
                    === String(column.assignment_id)
                && (
                    !column.parameter
                    || candidate.parameter === column.parameter
                )
            ),
        );
        const datasets = resultColumns.map((column, index) => ({
            column,
            color: chartColors[index % chartColors.length],
            points: samples.map((sample) => {
                if (sample.status === "failed") {
                    return null;
                }
                const reading = findReading(sample, column);
                if (!reading || !Number.isFinite(Number(reading.value))) {
                    return null;
                }
                return Number(reading.value);
            }),
        }));
        const values = datasets.flatMap(
            (dataset) => dataset.points.filter((value) => value !== null),
        );

        legend.replaceChildren();
        datasets.forEach((dataset) => {
            const item = document.createElement("span");
            item.className = "task-chart-legend-item";
            const swatch = document.createElement("span");
            swatch.className = "task-chart-legend-swatch";
            swatch.style.backgroundColor = dataset.color;
            item.append(swatch, document.createTextNode(dataset.column.label));
            legend.append(item);
        });

        const hasData = samples.length > 0 && values.length > 0;
        canvas.classList.toggle("d-none", !hasData);
        empty.classList.toggle("d-none", hasData);
        if (!hasData) {
            return;
        }

        window.requestAnimationFrame(() => {
            const width = Math.max(320, canvas.clientWidth);
            const height = 160;
            const ratio = window.devicePixelRatio || 1;
            canvas.width = Math.round(width * ratio);
            canvas.height = Math.round(height * ratio);
            const context = canvas.getContext("2d");
            context.setTransform(ratio, 0, 0, ratio, 0, 0);
            context.clearRect(0, 0, width, height);

            const plot = {left: 72, right: width - 18, top: 12, bottom: 118};
            let minimum = Math.min(...values);
            let maximum = Math.max(...values);
            const span = maximum - minimum;
            const margin = span > 0
                ? span * 0.08
                : Math.max(Math.abs(maximum) * 0.001, 0.001);
            minimum -= margin;
            maximum += margin;

            const styles = getComputedStyle(canvas);
            const foreground = styles.color || "#212529";
            const grid = "rgba(128, 128, 128, 0.25)";
            context.font = "12px system-ui, sans-serif";
            context.fillStyle = foreground;
            context.strokeStyle = grid;
            context.lineWidth = 1;

            for (let step = 0; step <= 5; step += 1) {
                const fraction = step / 5;
                const y = plot.bottom - fraction * (plot.bottom - plot.top);
                context.beginPath();
                context.moveTo(plot.left, y);
                context.lineTo(plot.right, y);
                context.stroke();
                const value = minimum + fraction * (maximum - minimum);
                context.textAlign = "right";
                context.textBaseline = "middle";
                context.fillText(value.toPrecision(6), plot.left - 8, y);
            }

            const xFor = (index) => plot.left + (
                samples.length === 1
                    ? 0
                    : index / (samples.length - 1)
                        * (plot.right - plot.left)
            );
            const yFor = (value) => plot.bottom - (
                (value - minimum) / (maximum - minimum)
                * (plot.bottom - plot.top)
            );
            datasets.forEach((dataset) => {
                context.strokeStyle = dataset.color;
                context.lineWidth = 1.75;
                context.beginPath();
                let drawing = false;
                dataset.points.forEach((value, index) => {
                    if (value === null) {
                        drawing = false;
                        return;
                    }
                    const x = xFor(index);
                    const y = yFor(value);
                    if (!drawing) {
                        context.moveTo(x, y);
                        drawing = true;
                    } else {
                        context.lineTo(x, y);
                    }
                });
                context.stroke();
            });

            const formatChartTime = (value) => new Date(value).toLocaleTimeString();
            context.fillStyle = foreground;
            context.textBaseline = "top";
            context.textAlign = "left";
            context.fillText(formatChartTime(samples[0].timestamp), plot.left, 128);
            context.textAlign = "right";
            context.fillText(
                formatChartTime(samples[samples.length - 1].timestamp),
                plot.right,
                128,
            );

            const baseImage = context.getImageData(
                0,
                0,
                canvas.width,
                canvas.height,
            );
            const restoreChart = () => {
                context.setTransform(1, 0, 0, 1, 0, 0);
                context.putImageData(baseImage, 0, 0);
                context.setTransform(ratio, 0, 0, ratio, 0, 0);
            };
            const highlightSample = (sampleIndex) => {
                restoreChart();
                const x = xFor(sampleIndex);
                context.strokeStyle = "rgba(128, 128, 128, 0.65)";
                context.lineWidth = 1;
                context.beginPath();
                context.moveTo(x, plot.top);
                context.lineTo(x, plot.bottom);
                context.stroke();

                const tooltipLines = [
                    formatDateTime(samples[sampleIndex].timestamp),
                ];
                datasets.forEach((dataset) => {
                    const value = dataset.points[sampleIndex];
                    if (value === null) {
                        return;
                    }
                    const reading = findReading(
                        samples[sampleIndex],
                        dataset.column,
                    );
                    const decimals = Number.isInteger(reading?.decimals)
                        ? reading.decimals
                        : dataset.column.decimals;
                    const formattedValue = Number.isInteger(decimals)
                        ? value.toFixed(decimals)
                        : String(value);
                    tooltipLines.push(
                        `${dataset.column.label}: ${formattedValue}`
                        + `${reading?.unit ? ` ${reading.unit}` : ""}`,
                    );
                    context.fillStyle = dataset.color;
                    context.strokeStyle = "#ffffff";
                    context.lineWidth = 1.5;
                    context.beginPath();
                    context.arc(x, yFor(value), 4.5, 0, Math.PI * 2);
                    context.fill();
                    context.stroke();
                });

                context.font = "12px system-ui, sans-serif";
                const tooltipWidth = Math.max(
                    ...tooltipLines.map((line) => context.measureText(line).width),
                ) + 20;
                const tooltipHeight = tooltipLines.length * 19 + 12;
                let tooltipX = x + 10;
                if (tooltipX + tooltipWidth > width - 4) {
                    tooltipX = x - tooltipWidth - 10;
                }
                const tooltipY = plot.top + 8;
                context.fillStyle = "rgba(33, 37, 41, 0.92)";
                context.fillRect(
                    tooltipX,
                    tooltipY,
                    tooltipWidth,
                    tooltipHeight,
                );
                context.fillStyle = "#ffffff";
                context.textAlign = "left";
                context.textBaseline = "top";
                tooltipLines.forEach((line, index) => {
                    context.fillText(
                        line,
                        tooltipX + 10,
                        tooltipY + 7 + index * 19,
                    );
                });
            };

            canvas.onmousemove = (event) => {
                const bounds = canvas.getBoundingClientRect();
                const pointerX = event.clientX - bounds.left;
                if (pointerX < plot.left || pointerX > plot.right) {
                    restoreChart();
                    return;
                }
                const fraction = (pointerX - plot.left) / (
                    plot.right - plot.left
                );
                const sampleIndex = samples.length === 1
                    ? 0
                    : Math.round(fraction * (samples.length - 1));
                highlightSample(sampleIndex);
            };
            canvas.onmouseleave = restoreChart;
        });
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

        if (instrument.is_power_supply) {
            const limits = instrument.voltage_limits;
            const mode = addField(fields, "Mode", "mode", "sweep", [
                ["fixed", "Fixed"],
                ["sweep", "Sweep"],
                ["cycle", "Cycle"],
            ]);
            const sweepBack = addField(
                fields,
                "Sweep Back",
                "sweep_back",
                "false",
                [
                    ["false", "No"],
                    ["true", "Yes"],
                ],
            );
            const fixedVoltage = addField(
                fields,
                "Set voltage (V)",
                "set_voltage",
                limits.minimum,
            );
            const start = addField(
                fields,
                "Start voltage (V)",
                "start_voltage",
                limits.minimum,
            );
            const stop = addField(
                fields,
                "Stop voltage (V)",
                "stop_voltage",
                String(Math.min(10, Number(limits.maximum))),
            );
            const step = addField(
                fields,
                "Voltage step (V)",
                "voltage_step",
                limits.step,
            );
            [start, stop, step].forEach((field) => {
                field.parentElement.className = "col-md-4";
            });
            [fixedVoltage, start, stop, step].forEach((field) => {
                field.min = limits.minimum;
                field.max = limits.maximum;
                field.step = limits.step;
            });
            const cycles = addField(
                fields,
                "Cycle count",
                "cycle_count",
                "1",
            );
            cycles.step = "1";
            cycles.min = "1";
            cycles.max = "100";
            const updateVoltageModeFields = () => {
                const fixed = mode.value === "fixed";
                const cycle = mode.value === "cycle";
                fixedVoltage.parentElement.classList.toggle(
                    "d-none",
                    !fixed,
                );
                [start, stop, step].forEach((field) => {
                    field.parentElement.classList.toggle(
                        "d-none",
                        fixed,
                    );
                });
                cycles.parentElement.classList.toggle(
                    "d-none",
                    !cycle,
                );
                sweepBack.parentElement.classList.toggle(
                    "d-none",
                    mode.value !== "sweep",
                );
            };
            mode.addEventListener("change", updateVoltageModeFields);
            updateVoltageModeFields();
            if (instrument.driver === "mock_rnd_320_3005p") {
                const tolerance = addField(
                    fields,
                    "Output tolerance (±)",
                    "output_tolerance_value",
                    "0",
                );
                tolerance.parentElement.className = "col-md-4";
                tolerance.min = "0";
                const toleranceUnit = addField(
                    fields,
                    "Tolerance unit",
                    "output_tolerance_unit",
                    "mV",
                    [
                        ["uV", "µV"],
                        ["mV", "mV"],
                        ["V", "V"],
                    ],
                );
                toleranceUnit.parentElement.className = "col-md-4";
                const updateToleranceUnit = () => {
                    const settings = {
                        uV: {max: "30000000", step: "1"},
                        mV: {max: "30000", step: "0.001"},
                        V: {max: "30", step: "0.000001"},
                    }[toleranceUnit.value];
                    tolerance.max = settings.max;
                    tolerance.step = settings.step;
                };
                toleranceUnit.addEventListener("change", updateToleranceUnit);
                updateToleranceUnit();
            }
            const readback = addField(
                fields,
                "Output voltage readback",
                "readback_voltage",
                "false",
                [
                    ["false", "No"],
                    ["true", "Yes — read after each trigger"],
                ],
            );
            if (instrument.driver === "mock_rnd_320_3005p") {
                readback.parentElement.className = "col-md-4";
            }
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
            if (instrument.driver === "mock-dmm") {
                sourceOptions.push(["virtual", "Virtual power supply"]);
            }
            addField(
                fields,
                "Source",
                "source",
                "external",
                sourceOptions,
            );
            if ([
                "agilent_34401a",
                "keysight_34461a",
            ].includes(instrument.driver)) {
                addField(
                    fields,
                    "Front-panel display during task",
                    "display_off",
                    "false",
                    [
                        ["false", "On"],
                        ["true", "Off"],
                    ],
                );
            }
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
                const visible = (
                    instrument.driver === "mock-dmm"
                    && functionField.value === "temperature"
                );
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
        const measurementMode = form.elements.measurement_mode;
        const countField = pane.querySelector(".task-count-field");
        const updateMeasurementFields = () => {
            const mode = measurementMode.value;
            countField.classList.toggle("d-none", mode !== "loop");
        };
        measurementMode.addEventListener("change", updateMeasurementFields);
        updateMeasurementFields();
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
                upsertTaskRow(payload);
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
        const active = ["pending", "running"].includes(row.dataset.status);
        deleteButton.disabled = active && !isAdmin;
        deleteButton.title = active
            ? "Stop the active task before deleting it."
            : "";
    };

    const setTaskRowData = (row, task) => {
        row.dataset.taskId = task.id;
        row.dataset.taskTitle = task.name;
        row.dataset.status = task.status;
        row.dataset.statusLabel = task.status_label;
        row.dataset.started = formatDateTime(task.started_at);
        row.dataset.measurementCount = task.sample_count;
        row.querySelector("td").textContent = String(task.id).padStart(4, "0");
        row.querySelector("th").textContent = task.name;
        row.querySelector(".task-row-started").textContent = (
            formatDateTime(task.started_at)
        );
        const state = row.querySelector(".task-row-state");
        const active = ["pending", "running"].includes(task.status);
        const stateLabels = {
            completed: "Completed",
            stopped: "Stopped",
            failed: "Failed",
        };
        state.textContent = active
            ? "Active"
            : stateLabels[task.status] || task.status_label;
        state.className = "task-row-state badge";
        state.classList.add({
            pending: "text-bg-primary",
            running: "text-bg-primary",
            completed: "text-bg-success",
            stopped: "text-bg-secondary",
            failed: "text-bg-danger",
        }[task.status] || "text-bg-secondary");
        if (selectedRow === row) {
            selectRow(row);
        }
    };

    const bindTaskRow = (row) => {
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
    };

    const upsertTaskRow = (task) => {
        let row = taskRows.find(
            (candidate) => candidate.dataset.taskId === String(task.id),
        );
        if (!row) {
            row = document.createElement("tr");
            row.className = "task-row";
            row.tabIndex = 0;
            row.setAttribute("aria-selected", "false");
            const identifier = document.createElement("td");
            const name = document.createElement("th");
            name.scope = "row";
            const started = document.createElement("td");
            started.className = "task-row-started";
            const stateCell = document.createElement("td");
            const state = document.createElement("span");
            state.className = "task-row-state badge";
            stateCell.append(state);
            row.append(identifier, name, started, stateCell);
            document.querySelector("#saved-task-empty-row")?.remove();
            document.querySelector("#saved-task-table tbody").prepend(row);
            taskRows.unshift(row);
            bindTaskRow(row);
        }
        setTaskRowData(row, task);
        filterRows();
        return row;
    };

    const renderTaskData = (pane, task) => {
        upsertTaskRow(task);
        pane.querySelector(".saved-task-heading").textContent = task.name;
        pane.querySelector(".saved-task-summary").textContent = (
            task.measurement_mode_label
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
        pane.querySelector(".saved-task-elapsed").textContent = formatElapsed(
            task.started_at,
            task.finished_at,
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
        pane.querySelector(".task-complete-button").classList.toggle(
            "d-none",
            task.status !== "stopped",
        );

        const rows = pane.querySelector(".task-sample-rows");
        const header = pane.querySelector(".task-results-header");
        header.replaceChildren();
        const idHeader = document.createElement("th");
        idHeader.textContent = "ID";
        header.append(idHeader);
        const timeHeader = document.createElement("th");
        timeHeader.textContent = "Time";
        header.append(timeHeader);
        const acquisitionHeader = document.createElement("th");
        acquisitionHeader.textContent = "Acquisition time";
        header.append(acquisitionHeader);
        const instruments = task.instruments || [];
        const resultColumns = task.result_columns || instruments.map(
            (instrument) => ({
                assignment_id: instrument.assignment_id,
                parameter: null,
                label: instrument.name,
            }),
        );
        pane.currentTask = task;
        if (pane.chartSamples) {
            const samplesByIndex = new Map(
                pane.chartSamples.map((sample) => [sample.index, sample]),
            );
            (task.samples || []).forEach((sample) => {
                samplesByIndex.set(sample.index, sample);
            });
            let mergedSamples = [...samplesByIndex.values()].sort(
                (left, right) => left.index - right.index,
            );
            const rangeSeconds = {
                hour: 3600,
                day: 86400,
                week: 604800,
                month: 2592000,
                year: 31536000,
            }[pane.querySelector(".task-chart-range").value];
            if (rangeSeconds && mergedSamples.length) {
                const latest = new Date(
                    mergedSamples[mergedSamples.length - 1].timestamp,
                ).getTime();
                mergedSamples = mergedSamples.filter((sample) => (
                    new Date(sample.timestamp).getTime()
                    >= latest - rangeSeconds * 1000
                ));
            }
            if (mergedSamples.length > 1200) {
                const stride = Math.ceil(mergedSamples.length / 1000);
                mergedSamples = mergedSamples.filter(
                    (_sample, index) => index % stride === 0
                        || index === mergedSamples.length - 1,
                );
            }
            pane.chartSamples = mergedSamples;
        }
        renderLiveChart(
            pane,
            {...task, samples: pane.chartSamples || task.samples},
            pane.chartResultColumns || resultColumns,
        );
        resultColumns.forEach((column) => {
            const cell = document.createElement("th");
            cell.textContent = column.label;
            header.append(cell);
        });

        rows.replaceChildren();
        [...(task.samples || [])]
            .filter(
                (sample) => sample.acquisition_time_seconds !== null
                    || sample.status === "failed",
            )
            .sort((left, right) => right.index - left.index)
            .forEach((sample) => {
                const row = document.createElement("tr");
                row.classList.toggle("table-danger", sample.status === "failed");
                if (sample.error) {
                    row.title = `FAILED: ${sample.error}`;
                }
                const idCell = document.createElement("td");
                idCell.textContent = String(sample.index).padStart(4, "0");
                if (sample.status === "failed") {
                    idCell.textContent += " FAILED";
                }
                row.append(idCell);
                const timeCell = document.createElement("td");
                timeCell.textContent = formatDateTime(sample.timestamp);
                row.append(timeCell);
                const acquisitionCell = document.createElement("td");
                acquisitionCell.textContent = (
                    sample.acquisition_time_seconds === null
                    || sample.acquisition_time_seconds === undefined
                )
                    ? "—"
                    : `${Number(sample.acquisition_time_seconds).toFixed(3)} s`;
                row.append(acquisitionCell);
                resultColumns.forEach((column) => {
                    const cell = document.createElement("td");
                    const reading = (sample.readings || []).find(
                        (candidate) => (
                            String(candidate.assignment_id)
                                === String(column.assignment_id)
                            && (
                                !column.parameter
                                || candidate.parameter === column.parameter
                            )
                        ),
                    );
                    if (reading) {
                        const decimals = Number.isInteger(reading.decimals)
                            ? reading.decimals
                            : column.decimals;
                        const value = Number.isInteger(decimals)
                            ? Number(reading.value).toFixed(decimals)
                            : reading.value;
                        cell.textContent = `${value} ${reading.unit}`;
                        cell.title = reading.parameter;
                    } else {
                        cell.textContent = "—";
                    }
                    row.append(cell);
                });
                rows.append(row);
            });

        const scrollContainer = rows.closest(".task-sample-table-scroll");
        const renderedRows = [...rows.children];
        if (scrollContainer && renderedRows.length > 20) {
            const headerHeight = header.closest("thead").getBoundingClientRect()
                .height;
            const rowsHeight = renderedRows.slice(0, 20).reduce(
                (height, row) => height + row.getBoundingClientRect().height,
                0,
            );
            const measuredHeight = headerHeight + rowsHeight;
            scrollContainer.style.maxHeight = measuredHeight > 0
                ? `${Math.ceil(measuredHeight)}px`
                : "43.3125rem";
            scrollContainer.style.overflowY = "auto";
        }
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

    const fetchChartData = async (taskId, pane) => {
        const range = pane.querySelector(".task-chart-range").value;
        const response = await fetch(
            `/tasks/${taskId}/chart/?range=${encodeURIComponent(range)}`,
        );
        if (!response.ok) {
            throw new Error("Chart data could not be loaded.");
        }
        const payload = await response.json();
        pane.chartSamples = payload.samples || [];
        pane.chartResultColumns = payload.result_columns || [];
        if (pane.currentTask) {
            renderLiveChart(
                pane,
                {...pane.currentTask, samples: pane.chartSamples},
                pane.chartResultColumns,
            );
        }
    };

    const startPolling = (taskId, pane) => {
        const poll = () => {
            fetchTask(taskId, pane).catch((error) => {
                pane.querySelector(".task-detail-error").textContent = (
                    error.message
                );
            }).finally(() => {
                if (pane.taskPollTimer !== null) {
                    pane.taskPollTimer = window.setTimeout(poll, 1000);
                }
            });
        };
        pane.taskPollTimer = window.setTimeout(poll, 0);
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
                const confirmed = window.confirm(
                    `Stop task "${task.name}"?\n\n`
                    + "The current measurement sequence will be stopped.",
                );
                if (!confirmed) {
                    return;
                }
                const stopButton = pane.querySelector(".task-stop-button");
                stopButton.disabled = true;
                stopButton.textContent = "Stopping…";
                const csrfToken = document.querySelector(
                    '[name="csrfmiddlewaretoken"]',
                ).value;
                try {
                    const response = await fetch(`/tasks/${taskId}/stop/`, {
                        method: "POST",
                        headers: {"X-CSRFToken": csrfToken},
                    });
                    const contentType = (
                        response.headers.get("content-type") || ""
                    );
                    const payload = contentType.includes("application/json")
                        ? await response.json()
                        : {};
                    if (!response.ok) {
                        throw new Error(
                            payload.error || "Task could not be stopped.",
                        );
                    }
                } catch (error) {
                    pane.querySelector(".task-detail-error").textContent = (
                        error.message
                    );
                    stopButton.disabled = false;
                    stopButton.textContent = "Stop";
                }
            },
        );
        pane.querySelector(".task-complete-button").addEventListener(
            "click",
            async () => {
                const confirmed = window.confirm(
                    `Mark task "${task.name}" as completed?`,
                );
                if (!confirmed) {
                    return;
                }
                const completeButton = pane.querySelector(
                    ".task-complete-button",
                );
                completeButton.disabled = true;
                try {
                    const csrfToken = document.querySelector(
                        '[name="csrfmiddlewaretoken"]',
                    ).value;
                    const response = await fetch(
                        `/tasks/${taskId}/complete/`,
                        {
                            method: "POST",
                            headers: {"X-CSRFToken": csrfToken},
                        },
                    );
                    const contentType = (
                        response.headers.get("content-type") || ""
                    );
                    const payload = contentType.includes("application/json")
                        ? await response.json()
                        : {};
                    if (!response.ok) {
                        throw new Error(
                            payload.error
                            || "Task could not be marked as completed.",
                        );
                    }
                    renderTaskData(pane, payload);
                } catch (error) {
                    pane.querySelector(".task-detail-error").textContent = (
                        error.message
                    );
                    completeButton.disabled = false;
                }
            },
        );
        pane.querySelector(".task-chart-range").addEventListener(
            "change",
            () => {
                pane.chartSamples = null;
                fetchChartData(taskId, pane).catch((error) => {
                    pane.querySelector(".task-detail-error").textContent = (
                        error.message
                    );
                });
            },
        );
        fetchChartData(taskId, pane).catch((error) => {
            pane.querySelector(".task-detail-error").textContent = error.message;
        });
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
            deleteButton.disabled = true;
        }
        if (!selectedRow) {
            const firstVisibleRow = taskRows.find(
                (row) => !row.classList.contains("d-none"),
            );
            if (firstVisibleRow) {
                selectRow(firstVisibleRow);
            }
        }
    };

    const deleteSelectedTask = async () => {
        if (!selectedRow || deleteButton.disabled) {
            return;
        }
        const taskId = selectedRow.dataset.taskId;
        const taskName = selectedRow.dataset.taskTitle;
        const confirmed = window.confirm(
            `Delete task "${taskName}"?\n\n`
            + "This permanently deletes the task and all its measurements.",
        );
        if (!confirmed) {
            return;
        }
        deleteButton.disabled = true;
        try {
            const csrfToken = document.querySelector(
                '[name="csrfmiddlewaretoken"]',
            ).value;
            const response = await fetch(`/tasks/${taskId}/delete/`, {
                method: "POST",
                headers: {"X-CSRFToken": csrfToken},
            });
            const contentType = response.headers.get("content-type") || "";
            const payload = contentType.includes("application/json")
                ? await response.json()
                : {};
            if (!response.ok) {
                throw new Error(
                    payload.error
                    || `Task could not be deleted (server returned `
                    + `${response.status}). Restart the OIL service and retry.`,
                );
            }

            const openTrigger = document.querySelector(
                `[data-open-task-id="${taskId}"]`,
            );
            if (openTrigger) {
                const pane = document.querySelector(
                    openTrigger.dataset.bsTarget,
                );
                closeTab(openTrigger.closest("li"), pane, openTrigger);
            }
            const deletedRow = selectedRow;
            selectedRow = null;
            deletedRow.remove();
            const rowIndex = taskRows.indexOf(deletedRow);
            if (rowIndex !== -1) {
                taskRows.splice(rowIndex, 1);
            }
            openButton.disabled = true;
            deleteButton.disabled = true;
            if (!taskRows.length) {
                const emptyRow = document.createElement("tr");
                emptyRow.id = "saved-task-empty-row";
                const cell = document.createElement("td");
                cell.className = "text-center text-muted py-4";
                cell.colSpan = 4;
                cell.textContent = "No saved tasks are available.";
                emptyRow.append(cell);
                document.querySelector("#saved-task-table tbody").append(
                    emptyRow,
                );
            } else {
                filterRows();
            }
        } catch (error) {
            window.alert(error.message);
            if (selectedRow) {
                selectRow(selectedRow);
            }
        }
    };

    taskRows.forEach(bindTaskRow);
    if (taskRows.length) {
        selectRow(taskRows[0]);
    }

    newButton.addEventListener("click", openNewTask);
    openButton.addEventListener("click", () => openSavedTask(selectedRow));
    deleteButton.addEventListener("click", deleteSelectedTask);
    statusFilter?.addEventListener("change", filterRows);

    taskRows
        .filter((row) => ["pending", "running"].includes(row.dataset.status))
        .forEach((row) => openSavedTask(row));
})();
