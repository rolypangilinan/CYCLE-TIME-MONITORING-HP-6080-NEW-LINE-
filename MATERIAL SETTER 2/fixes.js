// JavaScript fixes for the cycle time monitoring issues

// Fix 1: Stop timer properly when LINEOUT is submitted
function submitLineout() {
    const reason = document.getElementById("reasonSelect").value;
    
    if (reason === "") {
        alert("Please select a reason for lineout.");
        return;
    }
    
    let counterToBlock;
    let isNGLineout = false;
    
    if (ngDetectedCounter !== null) {
        counterToBlock = ngDetectedCounter;
        isNGLineout = true;
        ngDetectedCounter = null;
    } else {
        counterToBlock = statusCount;
    }
    
    // FIX: Stop timer before submitting lineout
    if (timerInterval !== null) {
        clearInterval(timerInterval);
        timerInterval = null;
        updateStatus("STATUS: STOPPED", "stopped");
    }
    
    blockAllSubsequentProcessesFromRunningCounter(counterToBlock);
    
    // Get current elapsed time
    const elapsedTime = document.getElementById("timer").innerText;
    
    // Send data to database - pass_ng depends on whether NG was clicked
    sendDataToDatabase(isNGLineout ? 'ng_lineout' : 'lineout', {
        kitting_no: counterToBlock.toString(),
        lineout_reason: reason,
        elapsed_time: elapsedTime
    });
    
    console.log(`Process ${processNumber} Lineout - Reason: ${reason} - Counter: ${counterToBlock}`);
    
    // Close modal
    closeLineoutModal();
    
    // Reset timer to 00:00 after LINEOUT
    seconds = 0;
    document.getElementById("timer").innerText = formatTime(seconds);
    
    // Show confirmation
    alert(`Lineout submitted successfully!\nReason: ${reason}\nCounter: ${counterToBlock}\n\nProcess ${processNumber + 1} cannot run counter ${counterToBlock}`);
}

// Fix 2: Enhanced sendDataToDatabase with better error handling
function sendDataToDatabase(action, data) {
    let url;
    
    switch(action) {
        case 'start':
            url = '/api/start_process';
            break;
        case 'stop':
            url = '/api/stop_process';
            break;
        case 'ng':
            url = '/api/ng_process';
            break;
        case 'ng_lineout':
            url = '/api/ng_lineout_process';
            break;
        case 'lineout':
            url = '/api/lineout_process';
            break;
        default:
            console.error('Unknown action:', action);
            return;
    }
    
    // Add process number to data
    data.process_no = processNumber;
    
    // Add retry logic for failed requests
    const maxRetries = 3;
    let retryCount = 0;
    
    function attemptSend() {
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(result => {
            if (result.success) {
                console.log('Data saved successfully:', result);
            } else {
                console.error('Failed to save data:', result.error);
                // Show error to user
                alert(`Failed to save data: ${result.error}`);
            }
        })
        .catch(error => {
            console.error('Error sending data to database:', error);
            retryCount++;
            
            if (retryCount < maxRetries) {
                console.log(`Retrying... Attempt ${retryCount} of ${maxRetries}`);
                setTimeout(attemptSend, 1000); // Wait 1 second before retry
            } else {
                alert('Failed to save data after multiple attempts. Please check your connection and try again.');
            }
        });
    }
    
    attemptSend();
}

// Fix 3: Persistent dropdown items management
const SHARED_DROPDOWN_ITEMS_KEY = 'SHARED_DROPDOWN_ITEMS';

// Function to save dropdown items to localStorage
function saveDropdownItems() {
    const select = document.getElementById("reasonSelect");
    if (!select) return;
    
    const options = [];
    for (let i = 1; i < select.options.length; i++) { // Skip first option (placeholder)
        options.push({
            value: select.options[i].value,
            text: select.options[i].textContent
        });
    }
    
    localStorage.setItem(SHARED_DROPDOWN_ITEMS_KEY, JSON.stringify(options));
    console.log('Dropdown items saved to localStorage');
}

// Function to load dropdown items from localStorage
function loadDropdownItems() {
    const select = document.getElementById("reasonSelect");
    if (!select) return;
    
    const savedItems = localStorage.getItem(SHARED_DROPDOWN_ITEMS_KEY);
    if (!savedItems) return;
    
    try {
        const options = JSON.parse(savedItems);
        
        // Clear existing options (except first placeholder)
        while (select.options.length > 1) {
            select.remove(1);
        }
        
        // Add saved options
        options.forEach(option => {
            const newOption = document.createElement("option");
            newOption.value = option.value;
            newOption.textContent = option.text;
            select.appendChild(newOption);
        });
        
        console.log('Dropdown items loaded from localStorage');
    } catch (error) {
        console.error('Error loading dropdown items:', error);
    }
}

// Enhanced addDropdownItem function that saves to localStorage
function addDropdownItem() {
    const newItem = prompt("Enter new reason to add to dropdown list:");
    
    if (newItem && newItem.trim() !== "") {
        const select = document.getElementById("reasonSelect");
        const option = document.createElement("option");
        option.value = newItem.toUpperCase();
        option.textContent = newItem.toUpperCase();
        select.appendChild(option);
        
        // Save to localStorage
        saveDropdownItems();
        
        alert(`"${newItem.toUpperCase()}" has been added to the dropdown list.`);
    }
}

// Initialize dropdown items when page loads
window.addEventListener('load', () => {
    // Load existing counter logic
    loadCounter();
    
    // Load dropdown items
    loadDropdownItems();
    
    // Store this process as the last visited
    localStorage.setItem('last_visited_process', processNumber.toString());
});

// Save dropdown items before page unloads
window.addEventListener('beforeunload', () => {
    saveCounter();
    saveDropdownItems();
});

// Fix for Process 3 and 4 database update issues
// Add this to the stopTimer function
function stopTimer() {
    // Allow STOP button to work even if timer reached maxSeconds
    // Check if timer is running or if status shows "TARGET REACHED"
    const currentStatus = document.getElementById("processStatus").innerText;
    
    if (timerInterval === null && !currentStatus.includes("TARGET REACHED")) {
        return;
    }
    
    // Clear timer if it's still running
    if (timerInterval !== null) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    
    // Increment counter on every STOP
    statusCount++;
    updateStatusNumber();
    saveCounter();
    
    // Get current elapsed time
    const elapsedTime = document.getElementById("timer").innerText;
    
    // Ensure we have a valid elapsed time
    const validElapsedTime = elapsedTime || "00:00";
    
    // Send data to database with explicit process number
    const data = {
        kitting_no: statusCount.toString(),
        elapsed_time: validElapsedTime,
        process_no: processNumber  // Explicitly include process number
    };
    
    console.log('Sending STOP data:', data);
    sendDataToDatabase('stop', data);
    
    seconds = 0;
    document.getElementById("timer").innerText = formatTime(seconds);
    updateStatus("STATUS: STOPPED", "stopped");
}

// Export functions for use in HTML files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        submitLineout,
        sendDataToDatabase,
        saveDropdownItems,
        loadDropdownItems,
        addDropdownItem,
        stopTimer
    };
}
