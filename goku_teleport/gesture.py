"""Pose geometry helpers, kept independent of camera and GUI code."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def joint_angle(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    """Return the angle ABC in degrees."""
    ba = np.asarray(a, dtype=np.float32) - np.asarray(b, dtype=np.float32)
    bc = np.asarray(c, dtype=np.float32) - np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(ba) * np.linalg.norm(bc))
    if denom < 1e-8:
        return 0.0
    cosine = float(np.clip(np.dot(ba, bc) / denom, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def is_v_sign(hand_landmarks: Sequence[Sequence[float]]) -> tuple[bool, str, float]:
    """Recognize an index-and-middle-finger V sign held anywhere in view.

    Landmarks use normalized MediaPipe x/y coordinates. The returned score is
    a confidence-like geometry score in [0, 1], not a model probability.
    """
    hand = np.asarray(hand_landmarks, dtype=np.float32)
    if hand.ndim != 2 or hand.shape[0] != 21 or hand.shape[1] < 2 or not np.isfinite(hand).all():
        return False, "hand landmarks unavailable", 0.0

    index_angle = joint_angle(hand[5, :2], hand[6, :2], hand[7, :2])
    middle_angle = joint_angle(hand[9, :2], hand[10, :2], hand[11, :2])
    ring_angle = joint_angle(hand[13, :2], hand[14, :2], hand[15, :2])
    pinky_angle = joint_angle(hand[17, :2], hand[18, :2], hand[19, :2])

    palm_width = float(np.linalg.norm(hand[5, :2] - hand[17, :2]))
    if palm_width < 1e-5:
        return False, "hand too small or edge-on", 0.0

    if min(index_angle, middle_angle) < 145.0:
        return False, "straighten index and middle fingers", min(index_angle, middle_angle) / 180.0

    gap_ratio = float(np.linalg.norm(hand[8, :2] - hand[12, :2])) / palm_width
    if gap_ratio < 0.42:
        return False, "separate index and middle fingers into a V", 0.35
    if gap_ratio > 1.45:
        return False, "keep the V sign comfortably open", 0.35

    if ring_angle > 165.0 or pinky_angle > 170.0:
        return False, "curl ring and little fingers", 0.45

    straight_quality = min(1.0, min(index_angle, middle_angle) / 180.0)
    spread_quality = max(0.0, 1.0 - abs(gap_ratio - 0.82) / 0.82)
    return True, "V sign recognized", float(np.clip(0.65 * straight_quality + 0.35 * spread_quality, 0, 1))
