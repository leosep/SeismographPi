document.addEventListener('DOMContentLoaded', function () {
    var ctx = document.getElementById('geophoneCanvas').getContext('2d');
    var alertBanner = document.getElementById('alertBanner');
    var eventsList = document.getElementById('eventsList');

    if (!ctx) {
        console.error('Failed to get canvas context');
        return;
    }

    var chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Geophone Data',
                data: [],
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1,
                pointRadius: 0,  // 100 Hz of points renders much faster without dots
                fill: false
            }]
        },
        options: {
            responsive: true,
            animation: false,  // disable animation: redraws every second at high
                                // sample rates look choppy otherwise
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'second',
                        tooltipFormat: 'HH:mm:ss.SSS',
                        displayFormats: {
                            second: 'HH:mm:ss',
                            minute: 'HH:mm',
                            hour: 'HH:mm'
                        },
                    },
                    ticks: { source: 'data' }
                },
                y: { type: 'linear', position: 'left' }
            }
        }
    });

    // --- Chart data polling -------------------------------------------------
    // This only reads data the acquisition daemon already saved; it no
    // longer triggers sensor reads or writes anything (that was removed:
    // having the browser's poll loop be responsible for sampling meant
    // data acquisition stopped whenever the tab was closed).
    function fetchChartData() {
        fetch('/data')
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data && data.timestamps && data.values) {
                    chart.data.labels = data.timestamps.map(function (t) { return new Date(t); });
                    chart.data.datasets[0].data = data.values.map(Number);
                    chart.update();
                } else {
                    console.error('Data format is incorrect:', data);
                }
            })
            .catch(function (error) { console.error('Error fetching data:', error); });
    }

    // --- P-wave alerts via Server-Sent Events -------------------------------
    function addEventToList(evt) {
        if (!eventsList) return;
        var li = document.createElement('li');
        var t = new Date(evt.triggered_at).toLocaleTimeString();
        li.textContent = t + ' — ratio ' + evt.peak_ratio.toFixed(2) +
            ' — peak ' + evt.peak_value;
        eventsList.prepend(li);
    }

    function showAlert(evt) {
        if (!alertBanner) return;
        alertBanner.textContent = 'P-wave detected at ' +
            new Date(evt.triggered_at).toLocaleTimeString() +
            ' (ratio ' + evt.peak_ratio.toFixed(2) + ')';
        alertBanner.classList.add('visible');
        clearTimeout(showAlert._hideTimer);
        showAlert._hideTimer = setTimeout(function () {
            alertBanner.classList.remove('visible');
        }, 8000);
    }

    function connectEventStream() {
        var source = new EventSource('/events/stream');

        source.onmessage = function (e) {
            try {
                var evt = JSON.parse(e.data);
                showAlert(evt);
                addEventToList(evt);
            } catch (err) {
                // Keep-alive comments arrive as empty messages; ignore parse errors.
            }
        };

        source.onerror = function () {
            // EventSource auto-reconnects on its own; this just logs visibility
            // into connection drops (e.g. daemon or Flask restart).
            console.warn('SSE connection lost, browser will retry automatically.');
        };
    }

    // Load recent event history once on page load (so a refresh doesn't
    // lose context of what already happened).
    fetch('/events')
        .then(function (r) { return r.json(); })
        .then(function (events) {
            events.slice().reverse().forEach(addEventToList);
        })
        .catch(function (err) { console.error('Error loading event history:', err); });

    fetchChartData();
    setInterval(fetchChartData, 1000);
    connectEventStream();
});
