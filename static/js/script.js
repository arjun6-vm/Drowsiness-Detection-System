// SafeDrive Geolocation Sync
function sendLocation(position) {
    const data = {
        lat: position.coords.latitude,
        lng: position.coords.longitude,
        accuracy: position.coords.accuracy,
        source: 'gps',
        timestamp: new Date().toISOString()
    };

    fetch('/update_location', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        // Location updated silently
    })
    .catch(error => {
        console.warn('Location update error:', error);
    });
}

function handleLocationError(error) {
    let msg = 'Unknown error';
    switch (error.code) {
        case error.PERMISSION_DENIED:
            msg = 'Location permission denied';
            break;
        case error.POSITION_UNAVAILABLE:
            msg = 'Location information unavailable';
            break;
        case error.TIMEOUT:
            msg = 'Location request timed out';
            break;
    }
    console.warn('Geolocation warning:', msg);
}

function requestLocation() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(sendLocation, handleLocationError, {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        });
    }
}

// Request location on load
if (typeof window !== 'undefined') {
    requestLocation();
    if (navigator.geolocation) {
        setInterval(() => {
            navigator.geolocation.getCurrentPosition(sendLocation, () => {}, {
                enableHighAccuracy: true
            });
        }, 60000);
    }
}
