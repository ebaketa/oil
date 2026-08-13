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
    const chart = panel.querySelector(".dmm-chart-canvas");
    let selectedFunction = panel.querySelector(".dmm-function")?.dataset.function;
    let timer = null;
    let hold = false;
    let values = [];
    let lastLiveSampleId = null;
    let displayDecimals = 3;
    let chartStatistics = null;
    const readOnly = panel.dataset.readOnly === "true";

    const fitReading = () => {
        const row = panel.querySelector(".dmm-reading-row");
        if (!row || !reading) return;
        const maximumSize = 192;
        reading.style.fontSize = `${maximumSize}px`;
        row.style.paddingInline = "0";
        const style = getComputedStyle(row);
        const gap = Number.parseFloat(style.columnGap || style.gap) || 0;
        const unitWidth = unit.getBoundingClientRect().width;
        const numberWidth = Math.max(reading.scrollWidth, 1);
        const widthPerPixel = numberWidth / maximumSize;
        const widthFit = (row.clientWidth - unitWidth - gap)
            / (widthPerPixel + 1);
        const heightFit = Math.max(0, row.clientHeight - 8);
        const fontSize = Math.max(
            24,
            Math.min(maximumSize, widthFit, heightFit),
        );
        reading.style.fontSize = `${fontSize}px`;
        row.style.paddingInline = `${fontSize / 2}px`;
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
        const guideColor = theme.getPropertyValue("--oil-panel-line").trim();
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
        const minimum = statisticMinimum - rangePadding;
        const maximum = statisticMaximum + rangePadding;
        const inset = 10;
        const labelWidth = 105;
        const plotStart = inset + labelWidth;
        const plotWidth = Math.max(1, bounds.width - inset * 2 - labelWidth);
        const plotHeight = Math.max(1, bounds.height - inset * 2);
        const yForValue = (value) => (
            inset + (maximum - value) * plotHeight / (maximum - minimum)
        );
        context.font = "12px ui-monospace, SFMono-Regular, Menlo, monospace";
        context.textBaseline = "middle";
        [
            [statisticMaximum, "MAX"],
            [average, "AVG"],
            [statisticMinimum, "MIN"],
        ].forEach(([value, name]) => {
            const y = yForValue(value);
            context.save();
            context.setLineDash([5, 5]);
            context.strokeStyle = name === "AVG" ? labelColor : guideColor;
            context.lineWidth = 1;
            context.beginPath();
            context.moveTo(plotStart, y);
            context.lineTo(plotStart + plotWidth, y);
            context.stroke();
            context.restore();
            context.fillStyle = labelColor;
            context.fillText(
                `${name} ${format(value)}`,
                inset,
                y,
            );
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
    const updateRange = (payload) => {
        const rangeText = payload.autorange !== false
            ? "AUTO"
            : `${payload.range_value} ${payload.unit}`;
        headerRange.textContent = rangeText;
        range.textContent = rangeText;
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
        const body = new URLSearchParams({function: selectedFunction});
        try {
            const response = await fetch(panel.dataset.measureUrl, {
                method: "POST",
                headers: {"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value},
                body,
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "Measurement failed.");
            setError("");
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
            if (!hold) reading.textContent = format(payload.value);
            unit.textContent = payload.unit;
            fitReading();
        } catch (caught) {
            setError(caught.message);
            if (timer) continuousButton.click();
        }
    };
    panel.querySelectorAll(".dmm-function").forEach((button) => {
        button.addEventListener("click", () => {
            selectedFunction = button.dataset.function;
            label.textContent = button.dataset.displayLabel.toUpperCase();
            unit.textContent = button.dataset.unit;
            values = [];
            chartStatistics = null;
            drawChart();
            panel.querySelectorAll(".dmm-function").forEach((item) => item.classList.remove("active"));
            button.classList.add("active");
            trigger();
        });
    });
    panel.querySelector(".dmm-trigger")?.addEventListener("click", trigger);
    continuousButton?.addEventListener("click", () => {
        if (timer) {
            window.clearInterval(timer); timer = null;
            continuousButton.textContent = "Continuous";
        } else {
            trigger(); timer = window.setInterval(trigger, 1000);
            continuousButton.textContent = "Stop";
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
    panel.querySelector(".dmm-function")?.classList.add("active");

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
                    displayDecimals = Number.isInteger(payload.decimals) ? payload.decimals : 3;
                    updateRange(payload);
                    chartStatistics = {
                        minimum: Number(payload.minimum),
                        maximum: Number(payload.maximum),
                        average: Number(payload.average),
                    };
                    if (livePosition) {
                        livePosition.textContent = `Task ${payload.task_id} · Sample ${payload.sample_id}`;
                    }
                    if (lastLiveSampleId === null && Array.isArray(payload.recent_values)) {
                        values = payload.recent_values.map(Number);
                    } else if (payload.sample_id !== lastLiveSampleId) {
                        values.push(Number(payload.value));
                        if (values.length > 10000) values = values.slice(-10000);
                    }
                    lastLiveSampleId = payload.sample_id;
                    drawChart();
                    panel.querySelector(".dmm-min").textContent = format(payload.minimum);
                    panel.querySelector(".dmm-max").textContent = format(payload.maximum);
                    panel.querySelector(".dmm-average").textContent = format(payload.average);
                    label.textContent = payload.parameter.toUpperCase();
                    reading.textContent = format(payload.value);
                    unit.textContent = payload.unit;
                    fitReading();
                }
            } catch (caught) {
                setError(caught.message);
            }
        };
        pollTaskReading();
        window.setInterval(pollTaskReading, 1000);
    }
    window.requestAnimationFrame(fitReading);
})();
