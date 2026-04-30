/**
 * Garden Watering System - Frontend JavaScript
 * 
 * Features:
 * - Payload verification for all valve operations
 * - Clock synchronization with browser time
 * - Schedule management UI
 * - Real-time valve status updates
 */

// Configuration
const PAYLOAD_SECRET = 'garden-valve-2024';  // Must match backend
const TIME_WINDOW_SECONDS = 300;  // 5 minutes

// State
let currentSchedule = {};
let timeDifference = 0;  // Browser time - System time

// ==================== Payload Verification ====================

/**
 * Generate a SHA-256 hash for payload verification.
 * This prevents unauthorized valve operations by ensuring
 * the payload hasn't been tampered with.
 */
async function generatePayloadHash(valveId, action, timestamp) {
    const payloadContent = JSON.stringify({
        valve_id: valveId,
        timestamp: timestamp,
        action: action
    }, Object.keys({ valve_id: valveId, timestamp: timestamp, action: action }).sort());
    
    const encoder = new TextEncoder();
    const data = encoder.encode(payloadContent + PAYLOAD_SECRET);
    
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Create a verified payload for valve operations.
 * Includes timestamp for replay attack prevention.
 */
async function createVerifiedPayload(valveId, action = 'open') {
    const timestamp = Math.floor(Date.now() / 1000);
    const hash = await generatePayloadHash(valveId, action, timestamp);
    
    return {
        valve_id: valveId,
        timestamp: timestamp,
        action: action,
        payload_hash: hash
    };
}

/**
 * Verify payload structure before sending.
 * Additional validation on the client side.
 */
function validatePayload(payload) {
    if (!payload || typeof payload !== 'object') {
        return { valid: false, reason: 'Invalid payload structure' };
    }
    
    if (!Number.isInteger(payload.valve_id) || payload.valve_id < 0 || payload.valve_id > 3) {
        return { valid: false, reason: 'Invalid valve_id (must be 0-3)' };
    }
    
    if (!Number.isInteger(payload.timestamp)) {
        return { valid: false, reason: 'Invalid timestamp' };
    }
    
    const timeDiff = Math.abs(Math.floor(Date.now() / 1000) - payload.timestamp);
    if (timeDiff > TIME_WINDOW_SECONDS) {
        return { valid: false, reason: `Timestamp too old (${timeDiff}s > ${TIME_WINDOW_SECONDS}s)` };
    }
    
    if (!payload.payload_hash || typeof payload.payload_hash !== 'string') {
        return { valid: false, reason: 'Missing or invalid payload_hash' };
    }
    
    return { valid: true };
}

// ==================== Valve Control ====================

/**
 * Open a valve with payload verification.
 * Only one valve can be open at any time.
 */
async function openValve(valveId) {
    // Check if another valve is already open
    const activeCard = document.querySelector('.valve-card.active');
    if (activeCard && parseInt(activeCard.dataset.valve) !== valveId) {
        showToast('Another valve is already open! Close it first.', 'error');
        return;
    }
    
    try {
        // Create verified payload
        const payload = await createVerifiedPayload(valveId, 'open');
        
        // Validate payload before sending
        const validation = validatePayload(payload);
        if (!validation.valid) {
            showToast('Payload validation failed: ' + validation.reason, 'error');
            return;
        }
        
        // Send request
        const response = await fetch('/api/valve/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
            updateValveUI(valveId, true);
        } else {
            showToast(data.message || 'Failed to open valve', 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

/**
 * Close a valve with payload verification.
 */
async function closeValve(valveId) {
    try {
        const payload = await createVerifiedPayload(valveId, 'close');
        
        const validation = validatePayload(payload);
        if (!validation.valid) {
            showToast('Payload validation failed: ' + validation.reason, 'error');
            return;
        }
        
        const response = await fetch('/api/valve/close', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(data.message, 'success');
            updateValveUI(valveId, false);
        } else {
            showToast(data.message || 'Failed to close valve', 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

/**
 * Emergency stop - close all valves with payload verification.
 */
async function stopAllValves() {
    if (!confirm('⚠️ This will close ALL open valves. Continue?')) return;
    
    try {
        // Use valve 0 as the "controller" for the payload
        const payload = await createVerifiedPayload(0, 'stop_all');
        
        const response = await fetch('/api/valve/stop-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('All valves closed!', 'success');
            // Reset all valve UIs
            document.querySelectorAll('.valve-card').forEach(card => {
                updateValveUI(parseInt(card.dataset.valve), false);
            });
        } else {
            showToast(data.message || 'Failed to stop valves', 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

/**
 * Update valve UI based on open/closed state.
 */
function updateValveUI(valveId, isOpen) {
    const card = document.querySelector(`.valve-card[data-valve="${valveId}"]`);
    if (!card) return;
    
    const indicator = card.querySelector('.valve-indicator');
    
    if (isOpen) {
        card.classList.add('active');
        indicator.classList.remove('closed');
        indicator.classList.add('open');
    } else {
        card.classList.remove('active');
        indicator.classList.remove('open');
        indicator.classList.add('closed');
    }
}

// ==================== Schedule Management ====================

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/**
 * Initialize the schedule editor UI.
 */
function initScheduleEditor() {
    const container = document.getElementById('schedule-container');
    container.innerHTML = '';
    
    DAYS.forEach(day => {
        const dayCard = document.createElement('div');
        dayCard.className = 'day-card';
        dayCard.innerHTML = `
            <div class="day-header">
                <span>${day}</span>
                <button class="add-slot-btn" onclick="addSlot('${day}')" title="Add schedule slot">+</button>
            </div>
            <div class="slots-list" id="slots-${day}">
                <!-- Slots will be added here -->
            </div>
        `;
        container.appendChild(dayCard);
    });
    
    loadSchedule();
}

/**
 * Load schedule from server.
 */
async function loadSchedule() {
    try {
        const response = await fetch('/api/schedule');
        const data = await response.json();
        currentSchedule = data.schedule;
        
        // Render schedule
        DAYS.forEach(day => {
            const slotsList = document.getElementById(`slots-${day}`);
            slotsList.innerHTML = '';
            
            const slots = currentSchedule[day] || [];
            slots.forEach((slot, index) => {
                addSlotElement(slotsList, day, slot.start_time, slot.duration_minutes, slot.valve_id, index);
            });
            
            if (slots.length === 0) {
                slotsList.innerHTML = '<p style="color: #999; font-style: italic;">No scheduled watering</p>';
            }
        });
    } catch (error) {
        console.error('Failed to load schedule:', error);
    }
}

/**
 * Add a new empty slot to a day.
 */
function addSlot(day) {
    const slotsList = document.getElementById(`slots-${day}`);
    
    // Remove placeholder if exists
    if (slotsList.querySelector('p')) {
        slotsList.innerHTML = '';
    }
    
    addSlotElement(slotsList, day, '08:00', 15, 0);
}

/**
 * Add a slot element to the UI.
 */
function addSlotElement(container, day, startTime, duration, valveId, index) {
    const slotItem = document.createElement('div');
    slotItem.className = 'slot-item';
    slotItem.innerHTML = `
        <input type="time" value="${startTime}" onchange="updateSlot('${day}', ${index || 'new'}, 'start_time', this.value)">
        <select onchange="updateSlot('${day}', ${index || 'new'}, 'valve_id', this.value)">
            <option value="0" ${valveId === 0 ? 'selected' : ''}>Valve 1</option>
            <option value="1" ${valveId === 1 ? 'selected' : ''}>Valve 2</option>
            <option value="2" ${valveId === 2 ? 'selected' : ''}>Valve 3</option>
            <option value="3" ${valveId === 3 ? 'selected' : ''}>Valve 4</option>
        </select>
        <input type="number" value="${duration}" min="1" max="120" onchange="updateSlot('${day}', ${index || 'new'}, 'duration_minutes', this.value)">
        <span>min</span>
        <button class="remove-slot" onclick="removeSlot('${day}', ${index})">×</button>
    `;
    container.appendChild(slotItem);
}

/**
 * Update a slot value.
 */
function updateSlot(day, index, field, value) {
    if (!currentSchedule[day]) {
        currentSchedule[day] = [];
    }
    
    if (index === 'new') {
        currentSchedule[day].push({ start_time: '', duration_minutes: 15, valve_id: 0 });
        index = currentSchedule[day].length - 1;
    }
    
    currentSchedule[day][index][field] = field === 'valve_id' ? parseInt(value) : value;
}

/**
 * Remove a slot.
 */
function removeSlot(day, index) {
    if (currentSchedule[day]) {
        currentSchedule[day].splice(index, 1);
        loadSchedule();  // Reload to refresh UI
    }
}

/**
 * Save schedule to server.
 */
async function saveSchedule() {
    // Validate schedule before saving
    for (const day of DAYS) {
        const slots = currentSchedule[day] || [];
        for (const slot of slots) {
            if (!slot.start_time || !slot.duration_minutes || !slot.valve_id) {
                showToast(`Invalid slot on ${day}`, 'error');
                return;
            }
            if (slot.valve_id < 0 || slot.valve_id > 3) {
                showToast(`Invalid valve_id on ${day}`, 'error');
                return;
            }
        }
    }
    
    try {
        const response = await fetch('/api/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ schedule: currentSchedule })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('Schedule saved successfully!', 'success');
        } else {
            showToast(data.message || 'Failed to save schedule', 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

// ==================== Time Synchronization ====================

/**
 * Synchronize system time with browser clock.
 * Called on page load and periodically.
 */
async function syncTime() {
    const browserTimestamp = Math.floor(Date.now() / 1000);
    
    try {
        const response = await fetch('/api/time/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timestamp: browserTimestamp })
        });
        
        const data = await response.json();
        
        if (data.synced) {
            timeDifference = data.time_diff;
            
            document.getElementById('browser-time').textContent = 
                new Date().toLocaleTimeString();
            document.getElementById('time-diff').textContent = 
                `${timeDifference > 0 ? '+' : ''}${timeDifference}s`;
            
            if (data.ntp_sync_needed) {
                showToast('⚠️ Large time difference detected. Consider running NTP sync.', 'warning');
            } else {
                showToast('Time synchronized!', 'success');
            }
        }
    } catch (error) {
        console.error('Failed to sync time:', error);
    }
}

/**
 * Get system time adjusted for time difference.
 */
function getAdjustedTime() {
    const now = new Date(Date.now() + timeDifference * 1000);
    return now;
}

/**
 * Update the current time display.
 */
function updateTime() {
    const adjusted = getAdjustedTime();
    document.getElementById('current-time').textContent = adjusted.toLocaleTimeString();
    document.getElementById('system-time').textContent = adjusted.toLocaleString();
}

// ==================== Utility Functions ====================

/**
 * Show a toast notification.
 */
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    
    setTimeout(() => {
        toast.className = 'toast hidden';
    }, 3000);
}

/**
 * Check connection status.
 */
function checkConnection() {
    const status = document.getElementById('connection-status');
    fetch('/api/status', { method: 'HEAD' })
        .then(() => {
            status.className = 'status-connected';
            status.textContent = '● Connected';
        })
        .catch(() => {
            status.className = 'status-disconnected';
            status.textContent = '● Disconnected';
        });
}

// ==================== Initialization ====================

document.addEventListener('DOMContentLoaded', function() {
    // Initialize schedule editor
    initScheduleEditor();
    
    // Sync time on load
    syncTime();
    
    // Update time every second
    setInterval(updateTime, 1000);
    
    // Check connection every 30 seconds
    setInterval(checkConnection, 30000);
    checkConnection();
    
    // Auto-save schedule every 5 minutes
    setInterval(() => {
        if (Object.keys(currentSchedule).length > 0) {
            saveSchedule();
        }
    }, 300000);
});
