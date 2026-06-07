// UI Elements
const statusDiv = document.getElementById('location-status');
const retryBtn = document.getElementById('retry-location-btn');

function updateStatus(message, isError = false) {
    if (statusDiv) {
        statusDiv.style.display = 'block';
        statusDiv.textContent = message;
        statusDiv.style.backgroundColor = isError ? '#ffcccc' : '#d4edda';
        statusDiv.style.color = isError ? '#cc0000' : '#155724';
    }
}

// Function to send location to server
function sendLocation(position) {
    updateStatus("📍 GPS Location Active", false);
    retryBtn.style.display = 'none';

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
            console.log('Location updated:', data);
        })
        .catch((error) => {
            console.error('Error updating location:', error);
        });
}

// Error handler for geolocation
function handleLocationError(error) {
    let msg = "Unknown error";
    switch (error.code) {
        case error.PERMISSION_DENIED:
            msg = "Location permission denied. Please allow access for emergency alerts.";
            break;
        case error.POSITION_UNAVAILABLE:
            msg = "Location information is unavailable.";
            break;
        case error.TIMEOUT:
            msg = "The request to get user location timed out.";
            break;
        case error.UNKNOWN_ERROR:
            msg = "An unknown error occurred.";
            break;
    }
    console.warn(`Geolocation Error: ${msg}`);
    updateStatus(`⚠️ ${msg}`, true);
    retryBtn.style.display = 'inline-block';
}

function requestLocation() {
    if (navigator.geolocation) {
        updateStatus("📍 Requesting location...", false);
        navigator.geolocation.getCurrentPosition(sendLocation, handleLocationError, {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        });
    } else {
        updateStatus("❌ Geolocation is not supported by this browser.", true);
    }
}

// Event Listeners
if (retryBtn) {
    retryBtn.addEventListener('click', requestLocation);
}

// Request location immediately on load
requestLocation();

// Periodic update
if (navigator.geolocation) {
    setInterval(() => {
        navigator.geolocation.getCurrentPosition(sendLocation, (e) => console.log("Periodic update failed silently"), {
            enableHighAccuracy: true
        });
    }, 60000);
}
