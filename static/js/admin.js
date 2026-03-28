async function runDiscover() {
    const log = document.getElementById('discoverLog');
    const btn = document.getElementById('discoverBtn');
    const input = document.getElementById('targetResorts');
    
    const resortsText = input.value.trim();
    if (!resortsText) {
        alert("Please enter at least one resort name.");
        return;
    }

    log.innerHTML = 'Uploading target list...\n';
    btn.disabled = true;
    input.disabled = true;

    try {
        // Шаг 1: Сохраняем список курортов на сервере
        const response = await fetch('/admin/save_targets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ targets: resortsText })
        });

        if (!response.ok) throw new Error("Failed to upload targets");

        // Шаг 2: Запускаем скрипт и читаем поток (через EventSource)
        log.innerHTML += 'Starting local pipeline...\n\n';
        const source = new EventSource(`/admin/run/discover`);

        source.onmessage = function(event) {
            if (event.data === '__DONE__') {
                source.close();
                btn.disabled = false;
                input.disabled = false;
                log.innerHTML += '\nDone!';
            } else {
                log.innerHTML += event.data + '\n';
                log.scrollTop = log.scrollHeight;
            }
        };

        source.onerror = function() {
            source.close();
            btn.disabled = false;
            input.disabled = false;
            log.innerHTML += '\nConnection lost or error occurred.';
        };

    } catch (error) {
        btn.disabled = false;
        input.disabled = false;
        log.innerHTML += `\nError: ${error.message}`;
    }
}