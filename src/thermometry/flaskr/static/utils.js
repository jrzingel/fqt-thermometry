// Common utility functions used for plotting

function capitalize(s) {
    // Capitalize the first letter of a string
    return s && String(s[0]).toUpperCase() + String(s).slice(1);
}

// On the page load, get the last day of data
function setDefaultTimestamps(hours_ago=24) {
    const now = new Date();
    const timeAgo = new Date(now.getTime() - now.getTimezoneOffset()*60*1000 - hours_ago*60*60*1000);

    document.getElementById("startTime").value = timeAgo.toISOString().slice(0, 16);
}

function getSize(single=true, w=null) {
    if (w === null) w = document.getElementById("graphs").clientWidth;

    // System that determines if the plots are two columns or single column
    if (single || w < 700) {
        // Single column
        return {
            width: w,
            height: Math.max(w * 0.3, 200)
        }
    } else {
        // Double column
        return {
            width: Math.floor(w / 2),
            height: Math.min(w * 0.25, 200)
        }
    }
}

function prepData(packed, keys) {
    // Unpack the data into a form uPlot likes
    let data = [packed["times"]];
    for (let key of keys) {
        data.push(packed["readings"][key]);
    }
    return data;
}

function now() {
    // Get the current UNIX timestamp
    return new Date().toISOString();
}

function formatNumber(value, dp=4) {
    // Convert the number to scientific notation if small enough
    return Math.abs(value) < Math.pow(10, -dp) && value !== 0
        ? Number(value.toExponential(dp)).toExponential().toString()
        : parseFloat(value.toFixed(dp)).toString();
}

function formatNumbers(values, dp=4) {
    // Format the axis ticks to scientific notation if necessary
    let formatted = new Array(values.length);
    for (let i = 0; i < values.length; i++) {
        formatted[i] = formatNumber(values[i], dp)
    }
    return formatted;
}

async function fetchFromAPI(server, fridge, sensors) {
    // Query the API for fridge sensor data
    const startTime = new Date(document.getElementById("startTime").value).toISOString();
    const endTime = now();
    
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
    // LEGACY METHOD
    const startTime = new Date(new Date().getTime() - 3 * 24 * 60 * 60 * 1000).toISOString();  // 3 days ago
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

async function getColdestFridgeTempsFromAPI(server, fridges) {
    // Query the API for the coldest fridge temps (only mxc and still but don't tell anyone....)
    const query = fridges.flatMap(x => [[x, 'mxc'], [x, 'still']]);
    let packed = await fetchFridgesFromAPI(server, query)

    // Returns data raw (don't let the function unpack it)
    let data = [packed["times"]];
    for (let key of fridges) {
        // Find whichever value is coldest
        data.push(packed["readings"][key + ".mxc"].map((x,i) => Math.min(x??Infinity, packed["readings"][key + ".still"][i]??Infinity)));
    }
    return data;
}

async function fetchLatestFridgeSensorsFromAPI(server, query) {
    const requestData = {
        query: query,
    };

    const response = await fetch(server + '/api/v1/gauges', {
        method: 'POST',
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(requestData)
    });
    return await response.json();
}
