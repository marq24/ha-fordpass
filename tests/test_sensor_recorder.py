"""Regression tests for HA's class-time Recorder exclusion cache.

Run with: python -m unittest discover -s tests
Integration classes and Tag metadata are loaded from their AST without HA imports.
The Entity double models Entity.__init_subclass__ and the Recorder state-info
handoff in HA Core 2026.11.0b0 (homeassistant/helpers/entity.py).
"""
import ast
import asyncio
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/fordpass"
SOURCE = ROOT / "sensor.py"
EXPECTED = frozenset({
    "json_src", "privacySettingsEvent", "customEvents",
    "xevPlugChargerStatusEvent", "indicators", "configurations", "customMetrics",
})


class Entity:
    _entity_component_unrecorded_attributes = frozenset()
    _unrecorded_attributes = frozenset()
    __combined_unrecorded_attributes = frozenset()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__combined_unrecorded_attributes = (
            cls._entity_component_unrecorded_attributes | cls._unrecorded_attributes
        )

    def __init__(self, **kwargs):
        self._tag = kwargs["a_tag"]
        self.coordinator = kwargs["coordinator"]

    async def async_internal_added_to_hass(self):
        self._state_info = {
            "unrecorded_attributes": self.__combined_unrecorded_attributes
        }


def load_tags():
    """Read every real Tag's key and exclusions, omitting API callbacks."""
    tree = ast.parse((ROOT / "const_tags.py").read_text(encoding="utf-8-sig"))
    tag_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Tag")
    tags = {}
    for node in tag_class.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if not isinstance(node.value.func, ast.Name) or node.value.func.id != "ApiKey":
            continue
        keywords = {kw.arg: kw.value for kw in node.value.keywords}
        excluded = keywords.get("excluded_attrs")
        tags[node.targets[0].id] = SimpleNamespace(
            key=ast.literal_eval(keywords["key"]),
            excluded_attrs=(frozenset(ast.literal_eval(excluded.args[0]))
                            if excluded is not None else None),
        )
    class TagMetadata(Enum):
        @property
        def excluded_attrs(self):
            return self.value.excluded_attrs

    return TagMetadata("Tag", tags)


def load_sensors(tags):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef)
             or isinstance(n, ast.AsyncFunctionDef) and n.name == "async_setup_entry"]
    class SensorEntity(Entity):
        # Ensure integration exclusions are combined with component exclusions.
        _entity_component_unrecorded_attributes = frozenset({"component_attribute"})

    class RestoreEntity(Entity):
        pass

    namespace = {
        "FordPassEntity": type("FordPassEntity", (Entity,), {}),
        "SensorEntity": SensorEntity,
        "RestoreEntity": RestoreEntity,
        "Any": object,
        "HomeAssistant": object,
        "ConfigEntry": object,
        "FordPassDataUpdateCoordinator": object,
        "ExtSensorEntityDescription": object,
        "Platform": SimpleNamespace(SENSOR="sensor"),
        "Tag": tags,
        "UNSUPPORTED": "unsupported",
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class RecorderExclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tags = load_tags()
        cls.sensors = load_sensors(cls.tags)

    def test_tag_definitions_and_class_time_union(self):
        expected = {
            "MESSAGES": {"json_src"},
            "EVENTS": {"privacySettingsEvent", "customEvents", "xevPlugChargerStatusEvent"},
            "METRICS": {"indicators", "configurations", "customMetrics"},
        }
        for tag in self.tags:
            self.assertEqual(tag.value.excluded_attrs, expected.get(tag.name))
        sensor_class = self.sensors["FordPassSensor"]
        self.assertEqual(sensor_class.__dict__["_unrecorded_attributes"], EXPECTED)
        self.assertIsInstance(sensor_class._unrecorded_attributes, frozenset)
        self.assertEqual(
            sensor_class._Entity__combined_unrecorded_attributes,
            EXPECTED | {"component_attribute"},
        )

    def test_recorder_receives_cached_union_for_all_sensors(self):
        for name in ("FordPassSensor", "FordPassFirmwareUpdateHistorySensor"):
            with self.subTest(sensor=name):
                sensor = self.sensors[name](
                    SimpleNamespace(has_ev_soc=True),
                    SimpleNamespace(tag=self.tags.MESSAGES),
                )
                self.assertNotIn("_unrecorded_attributes", vars(sensor))
                asyncio.run(sensor.async_internal_added_to_hass())
                self.assertEqual(sensor._state_info["unrecorded_attributes"],
                                 EXPECTED | {"component_attribute"})

    def test_instance_assignment_does_not_change_recorder_cache(self):
        # Demonstrate the old failure: instance values never reach state-info.
        class InstanceOnly(Entity):
            pass

        sensor = InstanceOnly(a_tag=None, coordinator=None)
        sensor._unrecorded_attributes = EXPECTED
        asyncio.run(sensor.async_internal_added_to_hass())
        self.assertEqual(sensor._state_info["unrecorded_attributes"], frozenset())

    def test_base_entity_does_not_assign_instance_exclusions(self):
        tree = ast.parse((ROOT / "__init__.py").read_text(encoding="utf-8-sig"))
        entity = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                      and n.name == "FordPassEntity")
        assignments = (n for n in ast.walk(entity)
                       if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store))
        self.assertNotIn("_unrecorded_attributes", [n.attr for n in assignments])

    def test_live_attributes_and_native_values_unchanged(self):
        for tag in (self.tags.MESSAGES, self.tags.EVENTS, self.tags.METRICS):
            with self.subTest(tag=tag):
                attributes = {key: "x" * 20000 for key in tag.value.excluded_attrs}
                attributes["retained"] = "still recorded"
                callbacks = SimpleNamespace(
                    get_attributes=lambda data, units: data,
                    get_state=lambda data, previous: 7,
                )
                coordinator = SimpleNamespace(has_ev_soc=True, data=attributes, units={})
                sensor = self.sensors["FordPassSensor"](coordinator, SimpleNamespace(tag=callbacks))
                asyncio.run(sensor.async_internal_added_to_hass())
                self.assertIs(sensor.extra_state_attributes, attributes)
                self.assertEqual(sensor.native_value, 7)
                self.assertEqual(sensor._previous_state, 7)
                recorded = {
                    key: value for key, value in sensor.extra_state_attributes.items()
                    if key not in sensor._state_info["unrecorded_attributes"]
                }
                self.assertEqual(recorded, {"retained": "still recorded"})

    def test_setup_uses_existing_sensor_classes(self):
        descriptions = [SimpleNamespace(tag=tag, state_class=None, skip_existence_check=True)
                        for tag in self.tags]
        coordinator = SimpleNamespace(
            data=None, has_ev_soc=True, vli="test", tag_supported_by_vehicle=lambda tag: True,
        )
        sensors = []
        self.sensors.update({
            "DOMAIN": "fordpass", "COORDINATOR_KEY": "coordinator", "ROOT_METRICS": "metrics",
            "SENSORS": descriptions,
            "_LOGGER": SimpleNamespace(debug=lambda message: None),
            "async_get": lambda hass: object(),
            "entity_platform": SimpleNamespace(
                async_get_current_platform=lambda: SimpleNamespace(domain="sensor")),
            "SensorStateClass": SimpleNamespace(TOTAL_INCREASING="total_increasing"),
            # Prevent the unrelated SOC device-class override in this harness.
            "SensorDeviceClass": SimpleNamespace(BATTERY="battery"),
            "replace": lambda description, **kwargs: description,
        })
        hass = SimpleNamespace(data={"fordpass": {"test": {"coordinator": coordinator}}})
        asyncio.run(self.sensors["async_setup_entry"](
            hass, SimpleNamespace(entry_id="test"), lambda entities, update: sensors.extend(entities),
        ))
        self.assertEqual(len(sensors), len(descriptions))
        for sensor, description in zip(sensors, descriptions):
            expected = ("FordPassFirmwareUpdateHistorySensor"
                        if description.tag == self.tags.FIRMWARE_UPDATE_HISTORY else "FordPassSensor")
            self.assertIs(type(sensor), self.sensors[expected])


if __name__ == "__main__":
    unittest.main()
