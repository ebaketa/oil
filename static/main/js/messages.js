document.querySelectorAll("[data-auto-dismiss]").forEach((message) => {
    const delay = Number.parseInt(message.dataset.autoDismiss, 10);

    window.setTimeout(() => {
        bootstrap.Alert.getOrCreateInstance(message).close();
    }, delay);
});
