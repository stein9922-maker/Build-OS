"""Cross-check the CPM engine against an independent brute-force method.

The reference does NOT use forward/backward passes. It enumerates every start-to-finish path
and derives everything from path lengths:
  * project duration D      = longest path
  * ES(n)                   = longest path leading INTO n (excluding n)
  * tail(n)                 = longest path leaving n (excluding n);  LF(n) = D - tail(n)
  * critical path count     = number of paths whose length equals D
Random networks are seeded, so the test is deterministic.
"""
import random
import unittest
from collections import defaultdict
from datetime import date

from buildos.models import Activity, Dependency
from buildos.scheduling.cpm import compute_schedule

START = date(2026, 11, 2)


def brute_force(durations, links):
    succs = defaultdict(list)
    has_pred = set()
    for p, s in links:
        succs[p].append(s)
        has_pred.add(s)
    paths = []

    def walk(node, trail):
        trail.append(node)
        if not succs[node]:
            paths.append(list(trail))
        for nxt in succs[node]:
            walk(nxt, trail)
        trail.pop()

    for node in durations:
        if node not in has_pred:
            walk(node, [])

    project_duration = max(sum(durations[n] for n in path) for path in paths)
    es = {n: 0 for n in durations}
    tail = {n: 0 for n in durations}
    for path in paths:
        running = 0
        for n in path:
            es[n] = max(es[n], running)
            running += durations[n]
        running = 0
        for n in reversed(path):
            tail[n] = max(tail[n], running)
            running += durations[n]
    expected = {}
    for n, d in durations.items():
        lf = project_duration - tail[n]
        expected[n] = (es[n], es[n] + d, lf - d, lf, (lf - d) - es[n])
    critical_paths = sum(1 for path in paths if sum(durations[n] for n in path) == project_duration)
    return project_duration, expected, critical_paths


def random_network(rng):
    n = rng.randint(1, 8)
    ids = rng.sample(range(100, 1000), n)  # ids deliberately unrelated to dependency order
    durations = {i: (0 if rng.random() < 0.25 else rng.randint(1, 6)) for i in ids}
    links = [
        (ids[i], ids[j]) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.35
    ]  # edges only go "forward" in the hidden order, so the network is acyclic
    rng.shuffle(links)
    return durations, links


class BruteForceComparisonTests(unittest.TestCase):
    CASES = 400

    def test_engine_matches_brute_force_on_random_networks(self):
        rng = random.Random(20261014)
        stats = {"with_float": 0, "multi_path": 0, "has_zero": 0, "disconnected": 0}
        for case in range(self.CASES):
            durations, links = random_network(rng)
            order = list(durations)
            rng.shuffle(order)  # also shuffle the order activities are handed to the engine
            activities = [
                Activity(id=i, project_id=1, code=f"N{i}", name="x", duration_days=durations[i])
                for i in order
            ]
            dependencies = [Dependency(k, 1, p, s) for k, (p, s) in enumerate(links, start=1)]

            result = compute_schedule(START, activities, dependencies)
            want_duration, want_rows, want_paths = brute_force(durations, links)

            with self.subTest(case=case, durations=durations, links=links):
                self.assertEqual(result.project_duration_days, want_duration)
                self.assertEqual(result.critical_path_count, want_paths)
                got = {
                    a.activity_id: (a.es, a.ef, a.ls, a.lf, a.total_float) for a in result.activities
                }
                self.assertEqual(got, want_rows)
                # schedule order must be a valid dependency order
                position = {a.activity_id: k for k, a in enumerate(result.activities)}
                for p, s in links:
                    self.assertLess(position[p], position[s])

            stats["with_float"] += any(r[4] > 0 for r in want_rows.values())
            stats["multi_path"] += want_paths > 1
            stats["has_zero"] += any(d == 0 for d in durations.values())
            stats["disconnected"] += len(links) < len(durations) - 1

        # The random generator must actually exercise the interesting situations,
        # otherwise a passing test would prove little.
        for name, count in stats.items():
            self.assertGreater(count, 20, f"random cases rarely covered: {name} ({count})")


if __name__ == "__main__":
    unittest.main()
