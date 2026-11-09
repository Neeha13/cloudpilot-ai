"""Backwards-compatible accessors. All data comes from the shared snapshot in dataset.py."""
from .dataset import SERVICES, get_dataset  # noqa: F401


def build_spend():
    return get_dataset()["spend"]


def build_resources():
    return get_dataset()["resources"]
