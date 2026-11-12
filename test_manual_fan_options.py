from app import MANUAL_FAN_TYPE_OPTIONS


def test_manual_fan_type_options_use_standard_brand_names():
    assert MANUAL_FAN_TYPE_OPTIONS == (
        "Ziehl-Abegg",
        "ebm-papst",
        "Standart + Plug",
        "Yok",
    )
