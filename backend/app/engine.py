from .dataset import get_dataset
from . import anomalies as anomaly_engine
from . import recommendations as rec_engine


def anomalies(dataset: dict | None = None):
    """Anomalies detected in the latest billing month (without lifecycle status)."""
    return anomaly_engine.current(dataset or get_dataset())


def anomaly_history(dataset: dict | None = None):
    """Walk-forward detections across every month in the dataset."""
    return anomaly_engine.detect_all(dataset or get_dataset())


def recommendations(dataset: dict | None = None):
    """Scored recommendations without lifecycle status (see main.py for the merged view)."""
    dataset = dataset or get_dataset()
    # Business impact uses spikes and new-service spend in the current month; gradual growth is too mild to boost priority.
    anomalous = {a["service"] for a in anomalies(dataset) if a["type"] != "gradual_growth"}
    return rec_engine.generate(dataset, anomalous)
