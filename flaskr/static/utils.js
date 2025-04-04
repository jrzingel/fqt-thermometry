// Common utility functions used for plotting

function capitalize(s) {
    // Capitalize the first letter of a string
    return s && String(s[0]).toUpperCase() + String(s).slice(1);
}

// On the page load, get the last day of data
function setDefaultTimestamps() {
    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - now.getTimezoneOffset()*60*1000 - 24*60*60*1000);

    document.getElementById("startTime").value = sevenDaysAgo.toISOString().slice(0, 16);
}

function getSize(single=true) {
    let w = document.getElementById("workspace").clientWidth;  // Scale everything based on this

    // System that determines if the plots are two columns or single column
    if (single || w < 700) {
        // Single column
        return {
            width: w * 0.97,
            height: w * 0.3
        }
    } else {
        // Double column
        return {
            width: w * 0.97 * 0.5 * 0.95,
            height: Math.min(w * 0.25, 200)
        }
    }
}

function prepData(packed, keys) {
    // Unpack the data into a form uPlot likes
    let data = [packed["timestamps"]];
    for (let key of keys) {
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
    const startTime = new Date(document.getElementById("startTime").value).toISOString();
    const endTime = new Date().toISOString();
    
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
