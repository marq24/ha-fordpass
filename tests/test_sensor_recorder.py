"""Dependency-free regression tests for scoped Recorder exclusions.

Run with: python -m unittest discover -s tests
The sensor classes are loaded without integration imports; the Entity double
models Home Assistant's class-time combination of unrecorded attributes.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/fordpass/sensor.py"


class Entity:
    _unrecorded_attributes = frozenset()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.combined_unrecorded_attributes = cls._unrecorded_attributes

    def __init__(self, **kwargs):
        self._tag = kwargs["a_tag"]
        self.coordinator = kwargs["coordinator"]


def load_sensors():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    namespace = {
        "FordPassEntity": Entity,
        "SensorEntity": type("SensorEntity", (), {}),
        "RestoreEntity": type("RestoreEntity", (), {}),
        "Any": object,
        "FordPassDataUpdateCoordinator": object,
        "ExtSensorEntityDescription": object,
        "Platform": SimpleNamespace(SENSOR="sensor"),
        "Tag": SimpleNamespace(SOC=object(), BATTERY=object()),
        "UNSUPPORTED": "unsupported",
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class RecorderExclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sensors = load_sensors()

    def test_scoped_class_time_exclusions(self):
        expected = {
            "FordPassMessagesSensor": {"json_src"},
            "FordPassEventsSensor": {
                "privacySettingsEvent", "customEvents", "xevPlugChargerStatusEvent"
            },
            "FordPassMetricsSensor": {"indicators", "configurations", "customMetrics"},
            "FordPassSensor": set(),
            "FordPassFirmwareUpdateHistorySensor": set(),
        }
        for name, excluded in expected.items():
            with self.subTest(sensor=name):
                sensor = self.sensors[name]
                self.assertEqual(sensor.combined_unrecorded_attributes, frozenset(excluded))
                self.assertIsInstance(sensor._unrecorded_attributes, frozenset)

    def test_live_attributes_and_native_values_unchanged(self):
        for name in ("FordPassMessagesSensor", "FordPassEventsSensor", "FordPassMetricsSensor"):
            with self.subTest(sensor=name):
                attributes = {
                    key: "x" * 20000
                    for key in self.sensors[name]._unrecorded_attributes
                }
                attributes["retained"] = "still recorded"
                tag = SimpleNamespace(
                    get_attributes=lambda data, units: data,
                    get_state=lambda data, previous: 7,
                )
                coordinator = SimpleNamespace(has_ev_soc=True, data=attributes, units={})
                sensor = self.sensors[name](coordinator, SimpleNamespace(tag=tag))
                self.assertIs(sensor.extra_state_attributes, attributes)
                self.assertEqual(sensor.native_value, 7)
                self.assertEqual(sensor._previous_state, 7)
                recorded = {
                    key: value for key, value in sensor.extra_state_attributes.items()
                    if key not in sensor.combined_unrecorded_attributes
                }
                self.assertEqual(recorded, {"retained": "still recorded"})
                self.assertGreater(len(str(attributes)), 16384)

    def test_setup_routes_only_target_tags(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
        setup = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                     and node.name == "async_setup_entry")
        routes = {}
        for node in ast.walk(setup):
            if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
                continue
            comparison = node.test
            if len(comparison.comparators) != 1:
                continue
            target = comparison.comparators[0]
            if not isinstance(target, ast.Attribute) or not isinstance(target.value, ast.Name):
                continue
            if target.value.id != "Tag":
                continue
            assignment = node.body[-1]
            if isinstance(assignment, ast.Assign) and isinstance(assignment.value, ast.Call):
                routes[target.attr] = assignment.value.func.id
        self.assertEqual(routes, {
            "FIRMWARE_UPDATE_HISTORY": "FordPassFirmwareUpdateHistorySensor",
            "MESSAGES": "FordPassMessagesSensor",
            "EVENTS": "FordPassEventsSensor",
            "METRICS": "FordPassMetricsSensor",
        })
        self.assertIn("sensor = FordPassSensor(coordinator, a_entity_description)",
                      ast.unparse(setup))


if __name__ == "__main__":
    unittest.main()
