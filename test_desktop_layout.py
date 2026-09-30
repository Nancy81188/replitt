import unittest

from desktop import initial_window_size


class DesktopLayoutTest(unittest.TestCase):
    def test_initial_window_size_fits_available_screen_and_caps_large_defaults(self):
        width, height, min_width, min_height = initial_window_size(1920, 1080)
        self.assertEqual((width, height), (1180, 720))
        self.assertEqual((min_width, min_height), (760, 480))

    def test_initial_window_size_preserves_usable_short_screen_bounds(self):
        width, height, min_width, min_height = initial_window_size(800, 540)
        self.assertEqual((width, height), (768, 468))
        self.assertLessEqual(min_width, width)
        self.assertLessEqual(min_height, height)

    def test_initial_window_size_scales_defaults_without_exceeding_display(self):
        width, height, min_width, min_height = initial_window_size(1200, 700, 1.5)
        self.assertEqual((width, height), (1168, 628))
        self.assertEqual((min_width, min_height), (1140, 628))


if __name__ == "__main__":
    unittest.main()