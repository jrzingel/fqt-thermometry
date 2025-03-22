// Common utility functions used for plotting

function capitalize(s) {
    // Capitalize the first letter of a string
    return s && String(s[0]).toUpperCase() + String(s).slice(1);
}

// On the page load, get the last 7 days of data
function setDefaultTimestamps() {
    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    document.getElementById("startTime").value = sevenDaysAgo.toISOString().slice(0, 16);
}

function getSize(div_w=1.0, div_h=1.0, min_width=0, max_height=Infinity) {
    let w = document.getElementById("workspace").offsetWidth;  // Scale everything based on this
    return {
        width: Math.max(w * 0.97 / div_w, min_width),
        height: Math.min(w * 0.3 / div_h, max_height)
    }
}

function prepData(packed) {
    // Unpack the data into a form uPlot likes
    let data = [packed["timestamps"]];
    for (let key in packed["readings"]) {
        data.push(packed["readings"][key]);
    }
    return data;
}

function now() {
    // Get the current UNIX timestamp
    return new Date().toISOString().slice(0, 16);
}

async function fetchFromAPI(server, fridge, sensors) {
    // Query the API for fridge sensor data
    const startTime = document.getElementById("startTime").value;
    const endTime = new Date().toISOString().slice(0, 16);
    const requestData = {
        earliest_timestamp: startTime,
        latest_timestamp: endTime,
        fridge: fridge,
        sensors: sensors
    };

    const response = await fetch(server + '/api/v1/range', {
        method: 'POST',
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(requestData)
    });
    return await response.json();
}

async function fetchFridgesFromAPI(server, query) {
    // Query the API for fridge sensor data
    const startTime = new Date(new Date().getTime() - 3 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16);  // 3 days ago
    const endTime = now();
    const requestData = {
        earliest_timestamp: startTime,
        latest_timestamp: endTime,
        query: query
    };

    const response = await fetch(server + '/api/v1/fridges', {
        method: 'POST',
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(requestData)
    });
    return await response.json();
}
