(() => {
    "use strict";
    const panel = document.querySelector("[data-generic-panel]");
    if (!panel) return;
    const readings = panel.querySelector("[data-generic-readings]");
    const errorBox = panel.querySelector("[data-generic-error]");
    const state = panel.querySelector("[data-generic-state]");
    const render = (items) => {
        readings.replaceChildren();
        items.forEach((item) => {
            const card = document.createElement("div");
            card.className = "col-md-4";
            card.innerHTML = `<div class="border rounded p-3 h-100"><div class="text-muted small">${item.parameter}</div><div class="display-6">${Number(item.value).toFixed(2)} <span class="fs-6">${item.unit}</span></div></div>`;
            readings.append(card);
        });
    };
    const poll = async () => {
        try {
            const response = await fetch(panel.dataset.measureUrl, {headers: {"X-Requested-With": "XMLHttpRequest"}});
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
