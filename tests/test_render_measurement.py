"""Windows PID reuse must not charge unrelated apps to a render."""
import unittest
from scripts.compare_renderers import owned_instances


class RenderMeasurementTests(unittest.TestCase):
    def test_recycled_parent_pid_does_not_include_an_older_unrelated_process(self):
        records={10:{'parent':1,'created':100},11:{'parent':10,'created':120},
                 12:{'parent':10,'created':50},13:{'parent':12,'created':70},
                 14:{'parent':11,'created':130}}
        self.assertEqual(set(owned_instances(records,10)),{10,11,14})

    def test_recycled_intermediate_pid_cannot_attach_its_previous_children(self):
        records={1:{'parent':0,'created':10},2:{'parent':1,'created':100},
                 3:{'parent':2,'created':50},4:{'parent':2,'created':101}}
        self.assertEqual(set(owned_instances(records,1)),{1,2,4})

    def test_root_exit_or_unreadable_root_is_not_a_new_tree(self):
        self.assertEqual(owned_instances({11:{'parent':10,'created':120}},10),{})
