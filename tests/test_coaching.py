import math
import unittest

from coaching import Coach
from demo import demo_pose
from tracker import EXERCISES, RepCounter


class CoachTests(unittest.TestCase):
    def test_simulated_cycles_for_every_exercise_and_side(self):
        for exercise in EXERCISES:
            for side in ("left", "right"):
                with self.subTest(exercise=exercise, side=side):
                    coach = Coach(exercise, side)
                    for frame in range(300):
                        t = frame / 30
                        obs = coach.process(demo_pose(exercise, t, side), 1280, 720, t)
                    self.assertEqual(coach.counter.reps, 2)
                    self.assertIsNotNone(obs.angle)

    def test_side_lock_and_confidence_loss(self):
        coach = Coach("curl")
        pose = demo_pose("curl", 0)
        coach.process(pose, 1280, 720, 0)
        self.assertEqual(coach.locked_side, "left")
        for index in (11, 13, 15):
            pose[index] = (*pose[index][:3], .1)
        obs = coach.process(pose, 1280, 720, .1)
        self.assertIsNone(obs.angle)
        self.assertEqual(coach.locked_side, "left")
        self.assertEqual(coach.counter.phase, "ready")
        coach.new_set()
        coach.process(pose, 1280, 720, .2)
        self.assertEqual(coach.locked_side, "right")

    def test_out_of_frame_and_nan_are_rejected(self):
        for x in (-.1, 1.1, math.nan):
            coach = Coach("curl", "left")
            pose = demo_pose("curl", 0)
            pose[15] = (x, .4, 0, .99)
            self.assertIsNone(coach.process(pose, 1280, 720, 0).angle)

    def test_curl_upper_arm_feedback(self):
        coach = Coach("curl", "left")
        pose = demo_pose("curl", 0)
        pose[13] = (.75, .28, 0, .99)
        obs = coach.process(pose, 1280, 720, 0)
        self.assertTrue(obs.warning)
        self.assertIn("upper arm", obs.cue)

    def test_pause_interrupt_does_not_bridge_repetition(self):
        coach = Coach("curl", "left")
        for frame in range(85):
            t = frame / 30
            coach.process(demo_pose("curl", t), 1280, 720, t)
        coach.interrupt()
        for frame in range(85, 145):
            t = frame / 30
            coach.process(demo_pose("curl", t), 1280, 720, t)
        self.assertEqual(coach.counter.reps, 0)

    def test_invalid_endpoints(self):
        with self.assertRaises(ValueError):
            Coach("squat", low=150, high=160)

    def test_fast_and_stale_repetitions_rejected(self):
        counter = RepCounter(EXERCISES["curl"], dwell=0, min_duration=.65)
        for t, angle in ((0, 175), (.1, 40), (.2, 175)):
            counter.update(angle, t)
        self.assertEqual(counter.reps, 0)
        for t, angle in ((1, 40), (30, 175)):
            counter.update(angle, t)
        self.assertEqual(counter.reps, 0)
