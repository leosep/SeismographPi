document.addEventListener('DOMContentLoaded', function() {
    var ctx = document.getElementById('geophoneCanvas').getContext('2d');

    if (ctx) {
        var chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],  // Will be populated with timestamps
                datasets: [{
                    label: 'Geophone Data',
                    data: [],  // Will be populated with values
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 1,
                    fill: false
                }]
            },
            options: {
                responsive: true,
                scales: {
                    x: {
                        type: 'time',  // Assuming timestamps are in date format
                        time: {
                            unit: 'second',  // Adjust as per your data granularity
                            tooltipFormat: 'll HH:mm:ss',  // Adjust tooltip format as needed
                            displayFormats: {
                                second: 'HH:mm:ss',
                                minute: 'HH:mm',
                                hour: 'HH:mm',
                                day: 'MMM D',
                                week: 'll',
                                month: 'MMM YYYY',
                                quarter: '[Q]Q - YYYY',
                                year: 'YYYY'
                            },
                        },
                        ticks: {
                            source: 'data'
                        }
                    },
                    y: {
                        type: 'linear',
                        position: 'left'
                    }
                }
            }
        });

        // Function to fetch data from the server and update the chart
        function fetchData() {
            fetch('/data')
                .then(response => response.json())
                .then(data => {
                    console.log('Fetched data:', data); // Debug log
                    // Ensure data format is correct
                    if (data && data.timestamps && data.values) {
                        // Convert timestamps to Date objects
                        chart.data.labels = data.timestamps.map(timestamp => new Date(timestamp));
                        chart.data.datasets[0].data = data.values.map(value => Number(value));  // Convert values to numbers
                        chart.update(); // Update chart with new data

                        // Call function to save geophone data
                        saveGeophoneData(data.timestamps, data.values);
                    } else {
                        console.error('Data format is incorrect:', data);
                    }
                })
                .catch(error => console.error('Error fetching data:', error));
        }

        // Function to save geophone data to the server
        function saveGeophoneData(timestamps, values) {
            fetch('/save_geophone_data', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    timestamps: timestamps,
                    values: values
                })
            })
            .then(response => {
                if (!response.ok) {
                    console.error('Failed to save geophone data:', response);
                }
            })
            .catch(error => console.error('Error saving geophone data:', error));
        }

        // Fetch data initially and then at regular intervals
        fetchData();
        setInterval(fetchData, 1000);  // Fetch data every second
    } else {
        console.error('Failed to get canvas context');
    }
});
