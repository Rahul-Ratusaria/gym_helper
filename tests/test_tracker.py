import unittest
from tracker import EXERCISES, RepCounter, joint_angle


class TrackerTests(unittest.TestCase):
    def feed(self, counter, angles):
        for t, angle in enumerate(angles):
            counter.update(angle, t * 0.2)

    def test_geometry(self):
        self.assertAlmostEqual(joint_angle((0, 0), (1, 0), (1, 1)), 90)
        self.assertIsNone(joint_angle((1, 0), (1, 0), (1, 1)))

    def test_complete_cycles_all_exercises(self):
        for exercise in EXERCISES.values():
            with self.subTest(exercise=exercise.title):
                counter = RepCounter(exercise)
                self.feed(counter, [175, 175, 120, 40, 40, 120, 175, 175, 175])
                self.assertEqual(counter.reps, 1)

    def test_partial_motion_does_not_count(self):
        counter = RepCounter(EXERCISES["curl"])
        self.feed(counter, [40, 40, 175, 175, 100, 100, 175, 175])
        self.assertEqual(counter.reps, 0)

    def test_tracking_loss_cancels_incomplete_rep(self):
        counter = RepCounter(EXERCISES["curl"])
        self.feed(counter, [175, 175, 40, 40, None, 175, 175])
        self.assertEqual(counter.reps, 0)

    def test_single_frame_spike_does_not_count(self):
        counter = RepCounter(EXERCISES["curl"])
        self.feed(counter, [175, 175, 40, 120, 175, 175])
        self.assertEqual(counter.reps, 0)


if __name__ == "__main__":
    unittest.main()
