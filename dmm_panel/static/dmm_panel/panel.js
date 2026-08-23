(() => {
    const panel = document.querySelector(".dmm-panel");
    if (!panel) return;
    const reading = panel.querySelector(".dmm-reading");
    const unit = panel.querySelector(".dmm-unit");
    const label = panel.querySelector(".dmm-function-label");
    const headerRange = panel.querySelector(".dmm-header-range");
    const range = panel.querySelector(".dmm-range");
    const setError = (message) => {
        panel.dataset.error = message;
    };
    const livePosition = panel.querySelector(".dmm-live-position");
    const continuousButton = panel.querySelector(".dmm-continuous");
    const resolutionButton = panel.querySelector(".dmm-resolution");
    const triggerMode = panel.querySelector(".dmm-trigger-mode");
    const samplePosition = panel.querySelector(".dmm-sample-position");
    const autoRangeButton = panel.querySelector(".dmm-auto-range");
    const rangeUpButton = panel.querySelector(".dmm-range-up");
    const rangeDownButton = panel.querySelector(".dmm-range-down");
    const chart = panel.querySelector(".dmm-chart-canvas");
    const triggerLight = panel.querySelector(".dmm-trigger-light");
    const countModes = JSON.parse(
        document.querySelector("#dmm-count-modes")?.textContent || "{}",
    );
    const countModeLabels = JSON.parse(
        document.querySelector("#dmm-count-mode-labels")?.textContent || "{}",
    );
    const countModeNames = Object.keys(countModes);
    let selectedFunction = panel.querySelector(".dmm-function")?.dataset.function;
    let selectedRange = "auto";
    let selectedCountMode = countModeNames[0] || "50000";
    let timer = null;
    let hold = false;
    let localSampleCount = 0;
    let values = [];
    let lastLiveSampleId = null;
    let displayDecimals = 3;
    let chartStatistics = null;
    let chartZoom = 1;
    let chartScaleMode = "full";
    let fittedReadingWidth = null;
    let fittedReadingFontSize = 96;
    let taskVoltageRanges = countModes[selectedCountMode] || null;
    let readOnlyResolutionOverride = false;
    const readOnly = panel.dataset.readOnly === "true";
    const resolutionButtonText = (countMode) => (
        `Resolution ${countModeLabels[countMode] || countMode}`
    );

    const countModeDecimals = (value, countMode) => {
        const ranges = countModes[countMode] || [];
        const absoluteValue = Math.abs(Number(value));
        const activeRange = ranges.find(
            (candidate) => absoluteValue <= candidate,
        ) ?? ranges.at(-1);
        if (!activeRange) return displayDecimals;
        return Math.max(
            0,
            -Math.floor(Math.log10(activeRange / Number(countMode))),
        );
    };

    const selectedFunctionButton = () => panel.querySelector(
        `.dmm-function[data-function="${selectedFunction}"]`,
    );
    const availableRanges = () => (
        selectedFunction === "dc_voltage" && taskVoltageRanges
        || (selectedFunctionButton()?.dataset.ranges || "")
            .split(",").filter(Boolean).map(Number).filter(Number.isFinite)
    );
    const inferredRangeIndex = (ranges) => {
        const latestValue = values.length
            ? Math.abs(values[values.length - 1])
            : Math.abs(Number.parseFloat(reading.dataset.rawValue));
        const value = Number.isFinite(latestValue) ? latestValue : 0;
        const index = ranges.findIndex((candidate) => value <= candidate);
        return index === -1 ? ranges.length - 1 : index;
    };
    const updateRangeControls = () => {
        const ranges = availableRanges();
        const supportsAutorange = (
            selectedFunctionButton()?.dataset.autorange === "true"
        );
        const hasRanges = ranges.length > 0;
        const selectedIndex = selectedRange === "auto"
            ? inferredRangeIndex(ranges)
            : ranges.indexOf(Number(selectedRange));
        autoRangeButton.disabled = readOnly || !supportsAutorange;
        rangeUpButton.disabled = (
            readOnly || !hasRanges || selectedIndex >= ranges.length - 1
        );
        rangeDownButton.disabled = readOnly || !hasRanges || selectedIndex <= 0;
        autoRangeButton.classList.toggle("active", selectedRange === "auto");
        if (resolutionButton) {
            resolutionButton.disabled = (
                selectedFunction !== "dc_voltage" || countModeNames.length < 2
            );
        }
    };

    const pulseTrigger = () => {
        if (!triggerLight) return;
        triggerLight.classList.remove("active");
        void triggerLight.offsetWidth;
        triggerLight.classList.add("active");
    };

    const fitReading = () => {
        const row = panel.querySelector(".dmm-reading-row");
        if (!row || !reading) return;
        row.style.paddingInline = "0";
        const availableWidth = Math.max(0, row.clientWidth - 16);
        if (panel.getBoundingClientRect().width > 799) {
            fittedReadingWidth = availableWidth;
            fittedReadingFontSize = 96;
            reading.style.fontSize = "96px";
            if (unit) unit.style.fontSize = "48px";
            return;
        }
        if (
            fittedReadingWidth === null
            || Math.abs(fittedReadingWidth - availableWidth) > 1
        ) {
            fittedReadingWidth = availableWidth;
            fittedReadingFontSize = 96;
        }
        reading.style.fontSize = `${fittedReadingFontSize}px`;
        if (unit) unit.style.fontSize = `${fittedReadingFontSize / 2}px`;
        const readingWidth = reading.getBoundingClientRect().width;
        if (readingWidth > availableWidth && readingWidth > 0) {
            fittedReadingFontSize = Math.max(
                48,
                Math.floor(
                    fittedReadingFontSize * availableWidth / readingWidth,
                ),
            );
            reading.style.fontSize = `${fittedReadingFontSize}px`;
            if (unit) unit.style.fontSize = `${fittedReadingFontSize / 2}px`;
        }
    };

    const drawChart = () => {
        if (!chart) return;
        const bounds = chart.getBoundingClientRect();
        const scale = window.devicePixelRatio || 1;
        chart.width = Math.max(1, Math.round(bounds.width * scale));
        chart.height = Math.max(1, Math.round(bounds.height * scale));
        const context = chart.getContext("2d");
        const theme = getComputedStyle(panel);
        const traceColor = theme.getPropertyValue("--oil-chart-trace").trim();
        const labelColor = theme.getPropertyValue("--oil-chart-label").trim();
        const guideColor = theme.getPropertyValue("--oil-chart-guide").trim();
        context.scale(scale, scale);
        context.clearRect(0, 0, bounds.width, bounds.height);
        if (values.length < 2) return;
        const visible = values.slice(-120);
        const statisticMinimum = chartStatistics?.minimum ?? Math.min(...visible);
        const statisticMaximum = chartStatistics?.maximum ?? Math.max(...visible);
        const average = chartStatistics?.average
            ?? visible.reduce((sum, value) => sum + value, 0) / visible.length;
        const statisticRange = statisticMaximum - statisticMinimum;
        const rangePadding = statisticRange > 0
            ? statisticRange * 0.4
            : Math.max(Math.abs(statisticMinimum) * 0.4, 0.001);
        const isVoltage = unit.textContent.trim().startsWith("V");
        const visibleAverage = visible.reduce(
            (sum, value) => sum + value,
            0,
        ) / visible.length;
        const displayResolution = 10 ** (-displayDecimals);
        const maximumDeviation = Math.max(
            ...visible.map((value) => Math.abs(value - visibleAverage)),
        );
        const minimumDivision = Math.max(
            displayResolution,
            maximumDeviation / 9,
        );
        const niceCeiling = (value) => {
            const magnitude = 10 ** Math.floor(Math.log10(value));
            const normalized = value / magnitude;
            const nice = normalized <= 1 ? 1 : (normalized <= 2 ? 2 : (
                normalized <= 5 ? 5 : 10
            ));
            return nice * magnitude;
        };
        const voltageDivision = niceCeiling(minimumDivision);
        const chartCenter = isVoltage
            ? Math.round(visibleAverage / voltageDivision) * voltageDivision
            : average;
        const voltageHalfSpan = voltageDivision * 10;
        const visibleMinimum = Math.min(...visible);
        const visibleMaximum = Math.max(...visible);
        const voltagePadding = Math.max(
            Math.max(Math.abs(visibleMinimum), Math.abs(visibleMaximum)) * 0.1,
            displayResolution * 2,
        );
        const useFullScale = isVoltage && chartScaleMode === "full";
        const baseMinimum = useFullScale
            ? (visibleMaximum < 0 ? visibleMinimum - voltagePadding : 0)
            : (isVoltage
                ? chartCenter - voltageHalfSpan
                : statisticMinimum - rangePadding);
        const baseMaximum = useFullScale
            ? (visibleMaximum < 0 ? 0 : visibleMaximum + voltagePadding)
            : (isVoltage
                ? chartCenter + voltageHalfSpan
                : statisticMaximum + rangePadding);
        const baseSpan = Math.max(
            Number.EPSILON,
            baseMaximum - baseMinimum,
        );
        const minimum = useFullScale
            ? (baseMinimum < 0 ? baseMinimum * chartZoom : 0)
            : chartCenter - (baseSpan / 2) * chartZoom;
        const maximum = useFullScale
            ? (baseMaximum > 0 ? baseMaximum * chartZoom : 0)
            : chartCenter + (baseSpan / 2) * chartZoom;
        const guideMinimum = isVoltage ? minimum : statisticMinimum;
        const guideMaximum = isVoltage ? maximum : statisticMaximum;
        const inset = 10;
        context.font = '12px "Roboto Condensed", "Arial Narrow", Arial, sans-serif';
        context.textBaseline = "middle";
        const graphLabels = [
            guideMinimum,
            average,
            guideMaximum,
            minimum + (maximum - minimum) * 0.25,
            minimum + (maximum - minimum) * 0.75,
        ].map((value) => format(value));
        const labelWidth = Math.ceil(Math.max(
            ...graphLabels.map((value) => context.measureText(value).width),
        )) + 10;
        const plotStart = inset + labelWidth;
        const plotWidth = Math.max(1, bounds.width - inset * 2 - labelWidth);
        const plotHeight = Math.max(1, bounds.height - inset * 2);
        const yForValue = (value) => (
            inset + (maximum - value) * plotHeight / (maximum - minimum)
        );
        for (let division = 1; division < 20; division += 1) {
            const value = minimum + (maximum - minimum) * division / 20;
            const y = yForValue(value);
            const isHalfDivision = division === 5 || division === 15;
            const isCenterDivision = division === 10;
            context.save();
            context.strokeStyle = guideColor;
            context.globalAlpha = isCenterDivision
                ? 0.9
                : (isHalfDivision ? 0.6 : 0.3);
            context.lineWidth = isCenterDivision ? 1.5 : 1;
            context.beginPath();
            context.moveTo(plotStart, y);
            context.lineTo(plotStart + plotWidth, y);
            context.stroke();
            context.restore();
            if (isHalfDivision) {
                context.fillStyle = labelColor;
                context.fillText(format(value), inset, y);
            }
        }
        [
            [guideMaximum, "MAX"],
            [average, "AVG"],
            [guideMinimum, "MIN"],
        ].forEach(([value, name]) => {
            const y = yForValue(value);
            context.save();
            context.strokeStyle = name === "AVG" ? labelColor : guideColor;
            context.globalAlpha = name === "AVG" ? 1 : 0.9;
            context.lineWidth = name === "AVG" ? 2 : 1;
            context.beginPath();
            context.moveTo(plotStart, y);
            context.lineTo(plotStart + plotWidth, y);
            context.stroke();
            context.restore();
            context.fillStyle = labelColor;
            context.fillText(format(value), inset, y);
        });
        context.strokeStyle = traceColor;
        context.lineWidth = 2;
        context.beginPath();
        visible.forEach((value, index) => {
            const x = plotStart + index * plotWidth / (visible.length - 1);
            const y = yForValue(value);
            if (index === 0) context.moveTo(x, y);
            else context.lineTo(x, y);
        });
        context.stroke();
    };

    const fitPanelToViewport = () => {
        if (panel.getBoundingClientRect().width <= 799) {
            panel.style.height = "auto";
            return;
        }
        const top = panel.getBoundingClientRect().top;
        const footer = document.querySelector("body > .card > footer");
        const footerHeight = footer?.getBoundingClientRect().height || 0;
        const pageCard = document.querySelector("body > .card");
        const cardStyle = pageCard ? getComputedStyle(pageCard) : null;
        const bottomMargin = cardStyle
            ? Number.parseFloat(cardStyle.marginBottom) || 0
            : 0;
        const available = Math.max(
            0,
            document.documentElement.clientHeight
                - top
                - footerHeight
                - bottomMargin,
        );
        panel.style.height = `${available}px`;
    };
    window.requestAnimationFrame(fitPanelToViewport);
    window.addEventListener("resize", () => {
        fitPanelToViewport();
        fitReading();
        drawChart();
    });

    const format = (value, decimals = displayDecimals) => (
        Number(value).toFixed(decimals)
    );
    const formatReading = (value, decimals = displayDecimals) => {
        const formatted = format(value, decimals);
        return Number(value) >= 0 ? `+${formatted}` : formatted;
    };
    const displayFunctionName = (parameter) => ({
        "Voltage DC": "DC Voltage",
        "Voltage AC": "AC Voltage",
        "Current DC": "DC Current",
        "Current AC": "AC Current",
    }[parameter] || parameter);
    const setReading = (value, decimals = displayDecimals) => {
        const formatted = formatReading(value, decimals);
        const sign = formatted.slice(0, 1);
        const digits = formatted.slice(1);
        const decimalPoint = digits.indexOf(".");
        const splitAt = decimalPoint === -1 ? -1 : decimalPoint + 4;
        reading.dataset.rawValue = String(value);
        reading.replaceChildren();
        const signElement = document.createElement("span");
        signElement.className = "dmm-sign";
        signElement.textContent = sign;
        reading.append(signElement);
        if (splitAt > 0 && splitAt < digits.length) {
            reading.append(document.createTextNode(digits.slice(0, splitAt)));
            const digitGap = document.createElement("span");
            digitGap.className = "dmm-digit-gap";
            digitGap.setAttribute("aria-hidden", "true");
            reading.append(digitGap);
            reading.append(document.createTextNode(digits.slice(splitAt)));
        } else {
            reading.append(document.createTextNode(digits));
        }
    };
    const formatRange = (value, rangeUnit) => (
        rangeUnit === "V" && Number(value) < 1
            ? `${Number(value) * 1000} mV`
            : `${Number(value)} ${rangeUnit}`
    );
    const updateRange = (payload) => {
        let rangeText;
        if (payload.autorange !== false) {
            const ranges = availableRanges();
            const absoluteValue = Math.abs(Number(payload.value));
            const activeRange = ranges.find(
                (candidate) => absoluteValue <= candidate,
            ) ?? ranges.at(-1);
            rangeText = activeRange === undefined
                ? "AUTO"
                : `AUTO ${formatRange(activeRange, payload.unit)}`;
        } else {
            rangeText = formatRange(payload.range_value, payload.unit);
        }
        headerRange.textContent = rangeText;
        if (range) range.textContent = rangeText;
        updateRangeControls();
    };
    const updateStats = () => {
        if (!values.length) return;
        panel.querySelector(".dmm-min").textContent = format(Math.min(...values));
        panel.querySelector(".dmm-max").textContent = format(Math.max(...values));
        panel.querySelector(".dmm-average").textContent = format(
            values.reduce((sum, value) => sum + value, 0) / values.length,
        );
    };
    const trigger = async () => {
        if (!selectedFunction) return;
        const body = new URLSearchParams({
            function: selectedFunction,
            range: selectedRange,
            count_mode: selectedCountMode,
        });
        try {
            const response = await fetch(panel.dataset.measureUrl, {
                method: "POST",
                headers: {"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value},
                body,
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "Measurement failed.");
            setError("");
            pulseTrigger();
            localSampleCount += 1;
            if (samplePosition) samplePosition.textContent = `Sample: ${localSampleCount}`;
            displayDecimals = Number.isInteger(payload.decimals) ? payload.decimals : 3;
            updateRange(payload);
            values.push(Number(payload.value));
            if (values.length > 10000) values = values.slice(-10000);
            chartStatistics = {
                minimum: Math.min(...values),
                maximum: Math.max(...values),
                average: values.reduce((sum, value) => sum + value, 0) / values.length,
            };
            updateStats();
            drawChart();
            if (!hold) setReading(payload.value);
            unit.textContent = selectedFunctionButton()?.dataset.displayUnit
                || payload.unit;
            fitReading();
        } catch (caught) {
            setError(caught.message);
            if (timer) continuousButton.click();
        }
    };
    panel.querySelectorAll(".dmm-function").forEach((button) => {
        button.addEventListener("click", () => {
            selectedFunction = button.dataset.function;
            selectedRange = "auto";
            chartZoom = 1;
            label.textContent = button.dataset.displayLabel;
            unit.textContent = button.dataset.displayUnit;
            values = [];
            chartStatistics = null;
            drawChart();
            panel.querySelectorAll(".dmm-function").forEach((item) => item.classList.remove("active"));
            button.classList.add("active");
            updateRangeControls();
            trigger();
        });
    });
    autoRangeButton?.addEventListener("click", () => {
        selectedRange = "auto";
        chartZoom = 1;
        updateRangeControls();
        trigger();
    });
    const changeRange = (direction) => {
        const ranges = availableRanges();
        if (!ranges.length) return;
        const currentIndex = selectedRange === "auto"
            ? inferredRangeIndex(ranges)
            : ranges.indexOf(Number(selectedRange));
        const nextIndex = Math.max(
            0,
            Math.min(ranges.length - 1, currentIndex + direction),
        );
        selectedRange = String(ranges[nextIndex]);
        chartZoom = 1;
        updateRangeControls();
        trigger();
    };
    rangeUpButton?.addEventListener("click", () => changeRange(1));
    rangeDownButton?.addEventListener("click", () => changeRange(-1));
    resolutionButton?.addEventListener("click", () => {
        const currentIndex = countModeNames.indexOf(selectedCountMode);
        selectedCountMode = countModeNames[
            (currentIndex + 1) % countModeNames.length
        ];
        resolutionButton.textContent = resolutionButtonText(selectedCountMode);
        if (readOnly) {
            readOnlyResolutionOverride = true;
            const rawValue = Number(reading.dataset.rawValue);
            if (Number.isFinite(rawValue)) {
                displayDecimals = countModeDecimals(
                    rawValue,
                    selectedCountMode,
                );
                setReading(rawValue);
                updateStats();
                drawChart();
            }
        } else {
            taskVoltageRanges = countModes[selectedCountMode];
            selectedRange = "auto";
            chartZoom = 1;
            updateRangeControls();
            trigger();
        }
    });
    panel.querySelector(".dmm-trigger")?.addEventListener("click", trigger);
    continuousButton?.addEventListener("click", () => {
        if (timer) {
            window.clearInterval(timer); timer = null;
            continuousButton.textContent = "Continuous";
            if (triggerMode) triggerMode.textContent = "Manual Trigger";
        } else {
            trigger(); timer = window.setInterval(trigger, 1000);
            continuousButton.textContent = "Stop";
            if (triggerMode) triggerMode.textContent = "Auto Trigger";
        }
    });
    panel.querySelector(".dmm-hold")?.addEventListener("click", (event) => {
        hold = !hold; event.currentTarget.classList.toggle("active", hold);
    });
    panel.querySelector(".dmm-reset-stats")?.addEventListener("click", () => {
        values = [];
        chartStatistics = null;
        drawChart();
        [".dmm-min", ".dmm-max", ".dmm-average"].forEach((selector) => panel.querySelector(selector).textContent = "—");
    });
    const fullScaleButton = panel.querySelector(".dmm-chart-full-scale");
    const detailsButton = panel.querySelector(".dmm-chart-details");
    const selectChartScaleMode = (mode) => {
        chartScaleMode = mode;
        chartZoom = 1;
        fullScaleButton?.classList.toggle("active", mode === "full");
        detailsButton?.classList.toggle("active", mode === "details");
        drawChart();
    };
    fullScaleButton?.addEventListener("click", () => {
        selectChartScaleMode("full");
    });
    detailsButton?.addEventListener("click", () => {
        selectChartScaleMode("details");
    });
    panel.querySelector(".dmm-chart-zoom-in")?.addEventListener("click", () => {
        chartZoom = Math.max(1 / 32, chartZoom / 2);
        drawChart();
    });
    panel.querySelector(".dmm-chart-zoom-out")?.addEventListener("click", () => {
        chartZoom = Math.min(32, chartZoom * 2);
        drawChart();
    });
    panel.querySelector(".dmm-function")?.classList.add("active");
    updateRangeControls();

    if (readOnly) {
        const pollTaskReading = async () => {
            try {
                const response = await fetch(panel.dataset.liveUrl);
                const payload = await response.json();
                if (!response.ok) throw new Error(payload.error || "Live value could not be loaded.");
                if (!payload.active) {
                    setError("Task is no longer active. Reload the panel to enable controls.");
                    return;
                }
                if (payload.value !== undefined) {
                    setError("");
                    const parameterFunctions = {
                        "Voltage DC": "dc_voltage",
                        "Voltage AC": "ac_voltage",
                        "Current DC": "dc_current",
                        "Current AC": "ac_current",
                        Resistance: "resistance",
                        Temperature: "temperature",
                    };
                    selectedFunction = parameterFunctions[payload.parameter]
                        || selectedFunction;
                    displayDecimals = readOnlyResolutionOverride
                        ? countModeDecimals(payload.value, selectedCountMode)
                        : (Number.isInteger(payload.decimals) ? payload.decimals : 3);
                    taskVoltageRanges = Array.isArray(payload.voltage_ranges)
                        ? payload.voltage_ranges.map(Number)
                        : null;
                    if (
                        !readOnlyResolutionOverride
                        && payload.count_mode
                        && countModes[payload.count_mode]
                    ) {
                        selectedCountMode = payload.count_mode;
                        if (resolutionButton) {
                            resolutionButton.textContent = resolutionButtonText(
                                selectedCountMode,
                            );
                        }
                    }
                    updateRange(payload);
                    chartStatistics = {
                        minimum: Number(payload.minimum),
                        maximum: Number(payload.maximum),
                        average: Number(payload.average),
                    };
                    if (livePosition) {
                        livePosition.textContent = `Task ${payload.task_id}`;
                    }
                    if (samplePosition) samplePosition.textContent = `Sample: ${payload.sample_id}`;
                    if (lastLiveSampleId === null && Array.isArray(payload.recent_values)) {
                        values = payload.recent_values.map(Number);
                    } else if (payload.sample_id !== lastLiveSampleId) {
                        values.push(Number(payload.value));
                        if (values.length > 10000) values = values.slice(-10000);
                    }
                    if (payload.sample_id !== lastLiveSampleId) pulseTrigger();
                    lastLiveSampleId = payload.sample_id;
                    drawChart();
                    panel.querySelector(".dmm-min").textContent = format(payload.minimum);
                    panel.querySelector(".dmm-max").textContent = format(payload.maximum);
                    panel.querySelector(".dmm-average").textContent = format(payload.average);
                    label.textContent = displayFunctionName(payload.parameter);
                    setReading(payload.value);
                    const parameter = payload.parameter.toUpperCase();
                    if (payload.unit === "V") {
                        unit.textContent = parameter.includes("AC") ? "VAC" : "VDC";
                    } else if (payload.unit === "A") {
                        unit.textContent = parameter.includes("AC") ? "AAC" : "ADC";
                    } else {
                        unit.textContent = payload.unit;
                    }
                    fitReading();
                }
            } catch (caught) {
                setError(caught.message);
            }
        };
        pollTaskReading();
        window.setInterval(pollTaskReading, 1000);
    } else {
        continuousButton?.click();
    }
    window.requestAnimationFrame(fitReading);
})();
