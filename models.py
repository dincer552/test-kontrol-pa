from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


FILTER_IDS = ["Filtre 1", "Filtre 2", "Filtre 3", "Filtre 4", "Filtre 5"]

DAMPER_NAMES = ["Fresh", "Supply", "Return", "Exhaust", "Mix", "Bypass"]
SENSOR_NAMES = [
    "Fresh Air Sensor", "Supply Air Sensor", "Return Air Sensor", "Exhaust Air Sensor",
    "AfterCoil Air Sensor", "Mix Air Sensor", "AfterDxUnit Air Sensor", "AfterHeatRec Air Sensor",
    "Exchngr Leave Temp Sensor", "Room Temp Sensor 1", "Room Temp Sensor 2",
    "Room CO2 Sensor", "Room Hum Sensor", "Return CO2 Sensor", "Water Temp Sensor", "Return CO2 Air Sensor",
]


@dataclass
class TestControlState:
    order_no: str = ""
    project_name: str = ""
    ahu_name: str = ""
    user_name: str = ""
    notlar: str = ""

    fan_type: str = "Danfoss Ziehl-Abegg"
    supply_fan_count: int = 1
    return_fan_count: int = 1
    supply_airflow: str = ""
    return_airflow: str = ""
    airflow_control_ok: bool = True
    pressure_control_ok: bool = False

    damper_counts: Dict[str, int] = field(default_factory=lambda: {name: 0 for name in DAMPER_NAMES})
    filters: Dict[str, bool] = field(default_factory=lambda: {name: False for name in FILTER_IDS})
    sensors: Dict[str, str] = field(default_factory=lambda: {name: "-" for name in SENSOR_NAMES})
    manual_sensors: Dict[str, str] = field(default_factory=dict)

    rotor_enabled: bool = False
    rotor_mode: str = "Oransal"
    run_around: bool = False
    dx_enabled: bool = False
    dx_stage: int = 0
    humidifier_enabled: bool = False
    humidifier_stage: int = 0
    electrical_heater: bool = False
    electrical_stage_count: int = 3
    electrical_values: List[float] = field(default_factory=lambda: [0.0] * 12)
    pre_electrical_heater: bool = False
    pre_electrical_stage_count: int = 3
    pre_electrical_values: List[float] = field(default_factory=lambda: [0.0] * 12)
    valves: Dict[str, bool] = field(default_factory=dict)
    components: Dict[str, bool] = field(default_factory=dict)
    change_over: bool = False
    room_bms: bool = False
    temp_avg_en: bool = False

    c600_base_url: str = "http://127.0.0.1:4242"
    c600_json_id: str = "SupplyAirSensorMB\\TmpVal"
    c600_language: str = "en-US"
    c600_user: str = ""
    c600_connected: bool = False

    @property
    def fan_control_ok(self) -> bool:
        return bool(self.fan_type and self.supply_airflow and self.return_airflow)

    @property
    def damper_control_ok(self) -> bool:
        return any(value > 0 for value in self.damper_counts.values())

    @property
    def filter_control_ok(self) -> bool:
        return any(self.filters.values())

    @property
    def modules_ok(self) -> bool:
        return any((
            self.rotor_enabled,
            self.run_around,
            self.dx_enabled,
            self.humidifier_enabled,
            self.electrical_heater,
            self.pre_electrical_heater,
            self.change_over,
            self.room_bms,
            self.temp_avg_en,
        ))

    @property
    def sensors_ok(self) -> bool:
        return any(str(value).strip() not in ("", "-") for value in self.sensors.values())

    @property
    def c600_ok(self) -> bool:
        return self.c600_connected

    @property
    def user_ok(self) -> bool:
        return bool(self.user_name)

    @property
    def report_ok(self) -> bool:
        return bool(self.notlar)

    def set_project_info(self, order_no: str, project_name: str, ahu_name: str) -> None:
        self.order_no = order_no.strip()
        self.project_name = project_name.strip()
        self.ahu_name = ahu_name.strip()
