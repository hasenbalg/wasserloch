import os
def sync_system_time(browser_timestamp):
    """
    Synchronize system time with browser's clock.
    Called on each connection to ensure accurate scheduling.
    """
    try:
        browser_ts = int(browser_timestamp)
        current_ts = int(time.time())
        time_diff = browser_ts - current_ts
        
        logger.info("Time sync: browser=%d, system=%d, diff=%d seconds",
                   browser_ts, current_ts, time_diff)
        
        # Store the time difference for future calculations
        with open(SYSTEM_TIME_FILE, 'w') as f:
            json.dump({
                "browser_timestamp": browser_ts,
                "system_timestamp": current_ts,
                "time_difference": time_diff,
                "last_sync": int(time.time())
            }, f, indent=2)
        
        # If difference is significant (> 1 minute), suggest NTP sync
        if abs(time_diff) > 60:
            logger.warning("Large time difference detected: %d seconds", time_diff)
            return {"synced": True, "time_diff": time_diff, "ntp_sync_needed": abs(time_diff) > 300}
        
        return {"synced": True, "time_diff": time_diff, "ntp_sync_needed": False}
    except (ValueError, TypeError) as e:
        logger.error("Failed to sync time: %s", e)
        return {"synced": False, "error": str(e)}


def get_adjusted_time():
    """Get current time adjusted for browser-system time difference."""
    if os.path.exists(SYSTEM_TIME_FILE):
        try:
            with open(SYSTEM_TIME_FILE, 'r') as f:
                config = json.load(f)
            diff = config.get('time_difference', 0)
            return datetime.fromtimestamp(int(time.time()) + diff)
        except (json.JSONDecodeError, IOError, ValueError):
            pass
    return datetime.now()
