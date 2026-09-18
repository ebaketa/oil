(() => {
    "use strict";
    const panel = document.querySelector("[data-bmx-panel]");
    if (!panel) return;
    const readings = panel.querySelector("[data-bmx-readings]");
    const errorBox = panel.querySelector("[data-bmx-error]");
    const state = panel.querySelector("[data-bmx-state]");
    const labels = {
        Temperature: "Temperature",
        Humidity: "Humidity",
        Pressure: "Pressure",
    };
    const render = (items) => {
        readings.replaceChildren();
        items.forEach((item) => {
            const card = document.createElement("div");
            card.className = "col-md-4";
            const body = document.createElement("div");
            body.className = "border rounded p-3 h-100";
            const title = item.parameter.replace(/ channel \d+$/, "");
            const channel = item.parameter.match(/channel (\d+)$/)?.[1] || "";
            body.innerHTML = `<div class="text-muted small">${labels[title] || title} CH${channel}</div>`;
            const value = document.createElement("div");
            value.className = "display-6";
            value.textContent = Number(item.value).toFixed(title === "Pressure" ? 2 : 1);
            body.append(value, document.createTextNode(` ${item.unit}`));
            card.append(body);
            readings.append(card);
        });
    };
    const poll = async () => {
        try {
            const response = await fetch(panel.dataset.measureUrl, {
                headers: {"X-Requested-With": "XMLHttpRequest"},
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "Read failed.");
            render(payload.readings);
            state.textContent = "Connected";
            state.className = "badge text-bg-success";
            errorBox.textContent = "";
        } catch (error) {
            state.textContent = "Error";
            state.className = "badge text-bg-danger";
            errorBox.textContent = error.message;
        }
    };
    poll();
    window.setInterval(poll, 1000);
})();
