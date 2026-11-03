import unittest

import numpy as np

from goku_teleport.app import composite_teleport


class TeleportRendererTests(unittest.TestCase):
    def setUp(self):
        self.background = np.zeros((80, 100, 3), dtype=np.uint8)
        self.live = np.full((80, 100, 3), 180, dtype=np.uint8)
        self.mask = np.zeros((80, 100), dtype=np.float32)
        self.mask[15:70, 30:70] = 1.0

    def test_vanish_completes_to_background(self):
        result = composite_teleport(self.live, self.background, self.mask, 1.0, False)
        self.assertEqual(result.shape, self.live.shape)
        self.assertTrue(np.array_equal(result, self.background))

    def test_person_clears_before_silhouette_streaks_finish(self):
        result = composite_teleport(self.live, self.background, self.mask, 0.60, False)
        self.assertLess(float(result.mean()), 30.0)
        self.assertGreater(float(result.mean()), 0.0)

    def test_reappear_completes_to_live_camera(self):
        result = composite_teleport(self.live, self.background, self.mask, 1.0, True)
        self.assertGreater(int(result[35, 50, 0]), 150)
        self.assertEqual(tuple(result[3, 3]), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
