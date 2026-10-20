"""Current study choices, separate from task mechanics and the Socratic policy."""
# The present comparison deliberately uses a common two-task calibration.
# A newly registered task defaults to its own calibration; studies can override it.
CALIBRATION_TASKS={'MAB':('MAB','TBS'),'TBS':('MAB','TBS')}


def required_calibrations(task):
    return CALIBRATION_TASKS.get(task,(task,))
