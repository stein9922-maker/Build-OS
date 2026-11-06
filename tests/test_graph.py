import unittest

from buildos.scheduling.graph import build_graph, find_cycle, find_cycle_through_new_link


def _is_valid_cycle(links, cycle):
    """Every consecutive pair in the cycle (wrapping round) must be an existing link."""
    pairs = set(links)
    return all((cycle[i], cycle[(i + 1) % len(cycle)]) in pairs for i in range(len(cycle)))


class BuildGraphTests(unittest.TestCase):
    def test_builds_nodes_and_edges(self):
        g = build_graph([1, 2, 3], [(1, 2), (2, 3)])
        self.assertEqual(sorted(g.nodes), [1, 2, 3])
        self.assertEqual(sorted(g.edges), [(1, 2), (2, 3)])

    def test_isolated_activity_is_kept(self):
        self.assertIn(9, build_graph([1, 9], [])) 

    def test_unknown_activity_in_link_raises(self):
        with self.assertRaises(ValueError):
            build_graph([1, 2], [(1, 3)])


class FindCycleTests(unittest.TestCase):
    def test_no_cycle_in_chain_diamond_and_empty(self):
        self.assertIsNone(find_cycle(build_graph([], [])))
        self.assertIsNone(find_cycle(build_graph([1, 2, 3], [(1, 2), (2, 3)])))
        diamond = [(1, 2), (1, 3), (2, 4), (3, 4)]
        self.assertIsNone(find_cycle(build_graph([1, 2, 3, 4], diamond)))

    def test_two_node_cycle(self):
        links = [(1, 2), (2, 1)]
        cycle = find_cycle(build_graph([1, 2], links))
        self.assertEqual(sorted(cycle), [1, 2])
        self.assertTrue(_is_valid_cycle(links, cycle))

    def test_three_node_cycle_inside_larger_graph(self):
        links = [(0, 1), (1, 2), (2, 3), (3, 1), (3, 4)]
        cycle = find_cycle(build_graph(range(5), links))
        self.assertEqual(sorted(cycle), [1, 2, 3])
        self.assertTrue(_is_valid_cycle(links, cycle))

    def test_self_loop_is_a_cycle(self):
        self.assertEqual(find_cycle(build_graph([1], [(1, 1)])), [1])


class NewLinkCycleTests(unittest.TestCase):
    CHAIN = [(1, 2), (2, 3), (3, 4)]

    def setUp(self):
        self.graph = build_graph([1, 2, 3, 4, 5], self.CHAIN)

    def test_forward_shortcut_is_fine(self):
        self.assertIsNone(find_cycle_through_new_link(self.graph, 1, 4))

    def test_link_to_unconnected_activity_is_fine(self):
        self.assertIsNone(find_cycle_through_new_link(self.graph, 4, 5))
        self.assertIsNone(find_cycle_through_new_link(self.graph, 5, 1))

    def test_direct_reverse_link_detected(self):
        cycle = find_cycle_through_new_link(self.graph, 2, 1)
        self.assertEqual(cycle, [2, 1])

    def test_indirect_loop_detected_and_path_is_correct(self):
        cycle = find_cycle_through_new_link(self.graph, 4, 1)
        self.assertEqual(cycle, [4, 1, 2, 3])  # 4 -> 1 -> 2 -> 3 -> 4
        # the cycle only exists once the new link is added
        self.assertTrue(_is_valid_cycle([*self.CHAIN, (4, 1)], cycle))

    def test_self_link_detected(self):
        self.assertEqual(find_cycle_through_new_link(self.graph, 3, 3), [3])

    def test_unknown_node_raises(self):
        with self.assertRaises(ValueError):
            find_cycle_through_new_link(self.graph, 1, 99)

    def test_graph_is_not_modified(self):
        before = sorted(self.graph.edges)
        find_cycle_through_new_link(self.graph, 4, 1)
        self.assertEqual(sorted(self.graph.edges), before)


if __name__ == "__main__":
    unittest.main()
