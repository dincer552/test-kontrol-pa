from models import DAMPER_NAMES, FILTER_IDS, SENSOR_NAMES, TestControlState


def test_model_shape():
    state = TestControlState()
    assert len(DAMPER_NAMES) == 6
    assert len(FILTER_IDS) == 18
    assert len(SENSOR_NAMES) == 11
    assert state.supply_fan_count == 1
    assert state.return_fan_count == 1
    assert state.airflow_control_ok is True
    assert len(state.electrical_values) == 9


def test_project_info():
    state = TestControlState()
    state.set_project_info(" O1 ", " Project ", " HKS-12 ")
    assert state.order_no == "O1"
    assert state.project_name == "Project"
    assert state.ahu_name == "HKS-12"
