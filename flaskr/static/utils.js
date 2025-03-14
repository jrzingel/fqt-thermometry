// Common utility functions used for plotting


// On the page load, get the last 7 days of data
function setDefaultTimestamps() {
    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    document.getElementById("startTime").value = sevenDaysAgo.toISOString().slice(0, 16);
}

function getSize(divisor=1.0) {
    let w = document.getElementById("workspace").offsetWidth / divisor;  // Scale everything based on this
    return {
        width: w * 0.97,
        height: w * 0.3
    }
}


function prepData(packed) {
    // Unpack the data into a form uPlot likes
    let data = [packed["timestamps"]];
    for (let key in packed["readings"]) {
        data.push(packed["readings"][key]);
    }
    console.log(packed);
    console.log(data);
    return data;
}

function now() {
    // Get the current UNIX timestamp
    return new Date().toISOString().slice(0, 16);
}

async function fetchFromAPI(fridge, sensors) {
    // Query the API for fridge sensor data
    const startTime = document.getElementById("startTime").value;
    const endTime = new Date().toISOString().slice(0, 16);
    const requestData = {
        earliest_timestamp: startTime,
        latest_timestamp: endTime,
        fridge: fridge,
        sensors: sensors
    };

    const response = await fetch('http://127.0.0.1:5000/api/v1/range', {
        method: 'POST',
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(requestData)
    });
    return await response.json();
}

async function fetchFridgesFromAPI(query) {
    // Query the API for fridge sensor data
    const startTime = document.getElementById("startTime").value;
    const endTime = new Date().toISOString().slice(0, 16);
    const requestData = {
        earliest_timestamp: startTime,
        latest_timestamp: endTime,
        query: query
    };

    const response = await fetch('http://127.0.0.1:5000/api/v1/fridges', {
        method: 'POST',
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(requestData)
    });
    return await response.json();
}

function capitalize(s) {
    // Capitalize the first letter of a string
    return s && String(s[0]).toUpperCase() + String(s).slice(1);
}
