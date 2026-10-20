"""Compatibility facade. Task algorithms live in separate task modules."""
from .tasks.base import MODEL_VERSION as VERSION
from .tasks.mab import ARMS,KEYS,softmax,rl,log_dm,change_belief,mab_environment
from .tasks.tbs import tbs_context,tbs_pressure_model


def calibration_profile(task,history):
    from .tasks import get_task
    return get_task(task).calibrate(history)
