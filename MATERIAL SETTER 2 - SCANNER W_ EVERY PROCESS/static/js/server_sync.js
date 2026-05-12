/**
 * Server-Side Synchronization Module
 * Replaces localStorage-based state management with server-side APIs
 * for multi-device synchronization.
 */

const ServerSync = {
    // Cache for process state to reduce API calls
    _stateCache: {},
    _lastFetch: {},
    _cacheTTL: 1000, // Cache TTL in milliseconds

    /**
     * Get complete process state from server
     * @param {number} processNo - Process number (1-9)
     * @returns {Promise<Object>} Process state
     */
    async getProcessState(processNo) {
        const now = Date.now();
        if (this._stateCache[processNo] && (now - this._lastFetch[processNo]) < this._cacheTTL) {
            return this._stateCache[processNo];
        }

        try {
            const response = await fetch(`/api/get_process_state/${processNo}`);
            const data = await response.json();
            if (data.success) {
                this._stateCache[processNo] = data;
                this._lastFetch[processNo] = now;
                return data;
            }
            console.error('Failed to get process state:', data.error);
            return null;
        } catch (err) {
            console.error('Error fetching process state:', err);
            return null;
        }
    },

    /**
     * Sync counter with server (get the authoritative value)
     * @param {number} processNo - Process number
     * @param {number} browserCounter - Current browser counter value
     * @returns {Promise<number>} Authoritative counter value
     */
    async syncCounter(processNo, browserCounter) {
        try {
            const response = await fetch(`/api/sync_counter/${processNo}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ counter: browserCounter })
            });
            const data = await response.json();
            if (data.success) {
                return data.counter;
            }
            return browserCounter;
        } catch (err) {
            console.error('Error syncing counter:', err);
            return browserCounter;
        }
    },

    /**
     * Block a kitting number for all subsequent processes (on NG/LINEOUT)
     * @param {number} fromProcess - Process where NG/LINEOUT occurred
     * @param {number} kittingNo - Kitting number to block
     */
    async blockCounter(fromProcess, kittingNo) {
        try {
            const response = await fetch('/api/block_counter', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ from_process: fromProcess, kitting_no: kittingNo })
            });
            const data = await response.json();
            if (!data.success) {
                console.error('Failed to block counter:', data.error);
            }
            return data.success;
        } catch (err) {
            console.error('Error blocking counter:', err);
            return false;
        }
    },

    /**
     * Check if a kitting number is blocked for a process
     * @param {number} processNo - Process number
     * @param {number} kittingNo - Kitting number to check
     * @returns {Promise<boolean>} True if blocked
     */
    async isCounterBlocked(processNo, kittingNo) {
        try {
            const response = await fetch(`/api/is_counter_blocked/${processNo}/${kittingNo}`);
            const data = await response.json();
            return data.success && data.blocked;
        } catch (err) {
            console.error('Error checking blocked counter:', err);
            return false;
        }
    },

    /**
     * Get all blocked counters for a process
     * @param {number} processNo - Process number
     * @returns {Promise<Array>} List of blocked kitting numbers
     */
    async getBlockedCounters(processNo) {
        try {
            const response = await fetch(`/api/get_blocked_counters/${processNo}`);
            const data = await response.json();
            if (data.success) {
                return data.blocked_counters || [];
            }
            return [];
        } catch (err) {
            console.error('Error getting blocked counters:', err);
            return [];
        }
    },

    /**
     * Set active kitting for a process (when START is pressed)
     * @param {number} processNo - Process number
     * @param {number} kittingNo - Kitting number being worked on
     */
    async setActiveKitting(processNo, kittingNo) {
        try {
            const response = await fetch('/api/set_active_kitting', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ process_no: processNo, kitting_no: kittingNo })
            });
            const data = await response.json();
            return data.success;
        } catch (err) {
            console.error('Error setting active kitting:', err);
            return false;
        }
    },

    /**
     * Clear active kitting for a process (when STOP is pressed)
     * @param {number} processNo - Process number
     */
    async clearActiveKitting(processNo) {
        try {
            const response = await fetch(`/api/clear_active_kitting/${processNo}`, {
                method: 'POST'
            });
            const data = await response.json();
            return data.success;
        } catch (err) {
            console.error('Error clearing active kitting:', err);
            return false;
        }
    },

    /**
     * Check if a kitting number is being processed by another process
     * @param {number} kittingNo - Kitting number to check
     * @param {number} excludeProcess - Process to exclude from check (current process)
     * @returns {Promise<Object>} { active: boolean, process_no: number|null }
     */
    async isKittingActiveOnOtherProcess(kittingNo, excludeProcess) {
        try {
            const response = await fetch(`/api/is_kitting_active/${kittingNo}`);
            const data = await response.json();
            if (data.success && data.active && data.process_no !== excludeProcess) {
                return { active: true, process_no: data.process_no };
            }
            return { active: false, process_no: null };
        } catch (err) {
            console.error('Error checking active kitting:', err);
            return { active: false, process_no: null };
        }
    },

    /**
     * Get server timer state for a process
     * @param {number} processNo - Process number
     * @returns {Promise<Object|null>} Timer state or null if no active timer
     */
    async getServerTimer(processNo) {
        try {
            const response = await fetch(`/api/get_server_timer/${processNo}`);
            const data = await response.json();
            if (data.success && data.active) {
                return {
                    active: true,
                    kitting_no: data.kitting_no,
                    elapsed_seconds: data.elapsed_seconds
                };
            }
            return null;
        } catch (err) {
            console.error('Error getting server timer:', err);
            return null;
        }
    },

    /**
     * Start server-side timer tracking
     * @param {number} processNo - Process number
     * @param {number} kittingNo - Kitting number
     */
    async startServerTimer(processNo, kittingNo) {
        try {
            const response = await fetch(`/api/start_server_timer/${processNo}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kitting_no: kittingNo })
            });
            const data = await response.json();
            return data.success;
        } catch (err) {
            console.error('Error starting server timer:', err);
            return false;
        }
    },

    /**
     * Stop server-side timer tracking (called when STOP is pressed)
     * @param {number} processNo - Process number
     */
    async stopServerTimer(processNo) {
        try {
            const response = await fetch(`/api/stop_server_timer/${processNo}`, {
                method: 'POST'
            });
            const data = await response.json();
            console.log(`[ServerSync] Stopped server timer for Process ${processNo}`);
            return data.success;
        } catch (err) {
            console.error('Error stopping server timer:', err);
            return false;
        }
    },

    /**
     * Check if process can start a specific kitting number
     * @param {number} processNo - Process number
     * @param {number} kittingNo - Kitting number to start
     * @returns {Promise<Object>} { allowed: boolean, prev_completed: number }
     */
    async canStartKitting(processNo, kittingNo) {
        try {
            const response = await fetch(`/api/can_start_kitting/${processNo}/${kittingNo}`);
            const data = await response.json();
            if (data.success) {
                return {
                    allowed: data.allowed,
                    prev_completed: data.prev_completed,
                    prev_process: data.prev_process
                };
            }
            return { allowed: true, prev_completed: 0 };
        } catch (err) {
            console.error('Error checking can start kitting:', err);
            return { allowed: true, prev_completed: 0 };
        }
    },

    /**
     * Get the next available kitting number (skipping blocked ones)
     * @param {number} processNo - Process number
     * @param {number} currentCounter - Current counter value
     * @returns {Promise<number>} Next available kitting number
     */
    async getNextAvailableKitting(processNo, currentCounter) {
        const blocked = await this.getBlockedCounters(processNo);
        let nextKitting = currentCounter + 1;
        
        // Skip blocked kittings
        while (blocked.includes(nextKitting)) {
            console.log(`Kitting ${nextKitting} is blocked, skipping...`);
            nextKitting++;
        }
        
        return nextKitting;
    },

    /**
     * Initialize process state from server (call on page load)
     * @param {number} processNo - Process number
     * @returns {Promise<Object>} Initial state
     */
    async initializeProcessState(processNo) {
        const state = await this.getProcessState(processNo);
        if (!state) {
            return {
                counter: 0,
                timer: null,
                blocked_counters: [],
                active_kittings: {}
            };
        }
        return state;
    },

    /**
     * Poll for state changes (for real-time sync across devices)
     * @param {number} processNo - Process number
     * @param {function} callback - Callback with new state
     * @param {number} interval - Poll interval in ms (default 2000)
     * @returns {number} Interval ID for clearing
     */
    startPolling(processNo, callback, interval = 2000) {
        return setInterval(async () => {
            // Clear cache to force fresh fetch
            delete this._stateCache[processNo];
            const state = await this.getProcessState(processNo);
            if (state && callback) {
                callback(state);
            }
        }, interval);
    },

    /**
     * Stop polling
     * @param {number} intervalId - Interval ID from startPolling
     */
    stopPolling(intervalId) {
        if (intervalId) {
            clearInterval(intervalId);
        }
    }
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ServerSync;
}
