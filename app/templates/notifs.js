
let eventSource;
let reconnectAttempts = 0;

function connect() {
    const userId = "{{ current_user.id }}";
    eventSource = new EventSource(`{{ notif_server }}/notifications/stream?user_id=${userId}`);

    eventSource.onmessage = (event) => {
        console.log('received message');
        const data = JSON.parse(event.data);
        console.log(data);
        if(data['num_notifs'] > unreadNotifications) {      // unreadNotifications is set in base.html when the page loads initially.
            const outputs = document.getElementsByClassName('unreadNotificationDisplay');
            for (const el of outputs) {
                el.textContent = data['num_notifs'];
                document.title = document.title.replace(/^\(\d+\)\s*/, ''); // remove existing (number)
                document.title = `(${data['num_notifs']}) ${document.title}`;

                // also add 'red' class to sibling spans
                let sibling = el.previousElementSibling;
                while (sibling) {
                    if (sibling.tagName === 'SPAN') {
                        if (!sibling.classList.contains('red')) {
                            sibling.classList.add('red');
                        }
                        break;
                    }
                    sibling = sibling.previousElementSibling;
                }

                //play sound
                const sound = document.getElementById('notifSound');
                if (sound) {
                    sound.play().catch(err => {
                        console.warn("Audio play failed (possibly due to autoplay restrictions):", err);
                    });
                }

                if ('setAppBadge' in navigator) { // Show a number badge on pwa icon
                  navigator.setAppBadge(data['num_notifs']);
                }

            }
        }

    };

    eventSource.onerror = (err) => {
        console.error("SSE error:", err);
        eventSource.close();
        reconnectAttempts++;
        const timeout = Math.min(30000, 1000 * 2 ** reconnectAttempts);
        console.log(`Reconnecting in ${timeout / 1000}s...`);
        setTimeout(connect, timeout);
    };
}

connect();
