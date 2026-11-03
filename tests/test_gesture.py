import unittest

import numpy as np

from goku_teleport.gesture import is_v_sign, joint_angle


class GestureGeometryTests(unittest.TestCase):
    def test_straight_joint_angle(self):
        self.assertAlmostEqual(joint_angle((0, 0), (1, 0), (2, 0)), 180.0)

    def test_invalid_landmark_shape_is_rejected(self):
        accepted, reason, score = is_v_sign(np.zeros((4, 2)))
        self.assertFalse(accepted)
        self.assertIn("landmarks", reason)
        self.assertEqual(score, 0.0)

    def test_non_finite_landmarks_are_rejected(self):
        points = np.zeros((21, 3), dtype=np.float32)
        points[4, 0] = np.nan
        accepted, _, score = is_v_sign(points)
        self.assertFalse(accepted)
        self.assertEqual(score, 0.0)

    def test_spread_v_sign_is_accepted_without_face_landmarks(self):
        hand = np.zeros((21, 3), dtype=np.float32)
        hand[5, :2], hand[6, :2], hand[7, :2], hand[8, :2] = (0.47, 0.55), (0.47, 0.45), (0.47, 0.36), (0.43, 0.30)
        hand[9, :2], hand[10, :2], hand[11, :2], hand[12, :2] = (0.53, 0.55), (0.53, 0.45), (0.53, 0.36), (0.57, 0.30)
        hand[13, :2], hand[14, :2], hand[15, :2], hand[16, :2] = (0.57, 0.55), (0.57, 0.62), (0.59, 0.62), (0.61, 0.60)
        hand[17, :2], hand[18, :2], hand[19, :2], hand[20, :2] = (0.62, 0.55), (0.62, 0.61), (0.64, 0.62), (0.66, 0.60)
        accepted, reason, score = is_v_sign(hand)
        self.assertTrue(accepted, reason)
        self.assertGreaterEqual(score, 0.62)

    def test_joined_fingers_are_not_a_v_sign(self):
        hand = np.zeros((21, 3), dtype=np.float32)
        hand[5, :2], hand[6, :2], hand[7, :2], hand[8, :2] = (0.47, 0.55), (0.47, 0.45), (0.47, 0.36), (0.50, 0.30)
        hand[9, :2], hand[10, :2], hand[11, :2], hand[12, :2] = (0.53, 0.55), (0.53, 0.45), (0.53, 0.36), (0.51, 0.30)
        hand[13, :2], hand[14, :2], hand[15, :2] = (0.57, 0.55), (0.57, 0.62), (0.59, 0.62)
        hand[17, :2], hand[18, :2], hand[19, :2] = (0.62, 0.55), (0.62, 0.61), (0.64, 0.62)
        accepted, reason, _ = is_v_sign(hand)
        self.assertFalse(accepted)
        self.assertIn("V", reason)


if __name__ == "__main__":
    unittest.main()
