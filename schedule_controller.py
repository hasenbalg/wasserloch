import os
import json

def load_schedule():
    """Load watering schedule from file."""
    if os.path.exists(SCHEDULE_FILE):
        try:
            with open(SCHEDULE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    # Default empty schedule
    return {day: [] for day in DAYS}


def save_schedule(schedule):
    """Save watering schedule to file."""
    os.makedirs(os.path.dirname(SCHEDULE_FILE), exist_ok=True)
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(schedule, f, indent=2)
    logger.info("Schedule saved")