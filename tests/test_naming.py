from dilseries.naming import NEG_STEP, NamingConfig, Role, is_control_name, parse_names


def _parse(names, **config):
    parsed, _ = parse_names(names, NamingConfig(**config))
    return parsed


def test_undelimited_auto_detects_one_step_two_repeat_digits():
    names = [f"LE20{s}{r:02d}" for s in "123456789n" for r in range(1, 10)]
    parsed = _parse(names)
    assert parsed["LE20101"] == parsed["LE20101"].__class__(Role.SAMPLE, "LE20", "1", 1, parsed["LE20101"].layout)
    assert (parsed["LE20907"].series, parsed["LE20907"].step, parsed["LE20907"].repeat) == ("LE20", "9", 7)
    neg = parsed["LE20n09"]
    assert (neg.role, neg.series, neg.step, neg.repeat) == (Role.NEGATIVE, "LE20", NEG_STEP, 9)


def test_undelimited_single_digits():
    names = [f"TLIAA{s}{r}" for s in "123456n" for r in range(1, 10)]
    parsed = _parse(names)
    assert {(p.series, p.step, p.repeat) for p in parsed.values()} == {
        ("TLIAA", s if s != "n" else NEG_STEP, r) for s in "123456n" for r in range(1, 10)
    }


def test_two_families_with_different_layouts():
    names = ["LE20101", "LE20102", "LE20201", "LE20202", "LE20n01", "TLIAA11", "TLIAA12", "TLIAA21", "TLIAA22", "TLIAAn1"]
    parsed = _parse(names)
    assert (parsed["LE20202"].series, parsed["LE20202"].step, parsed["LE20202"].repeat) == ("LE20", "2", 2)
    assert (parsed["TLIAA21"].series, parsed["TLIAA21"].step, parsed["TLIAA21"].repeat) == ("TLIAA", "2", 1)


def test_configured_digits_resolve_ambiguous_zero_padding():
    names = [f"LIN{s:02d}{r:02d}" for s in range(1, 10) for r in range(1, 4)]
    auto = _parse(names)["LIN0302"]
    fixed = _parse(names, step_digits=2, repeat_digits=2)["LIN0302"]
    assert (auto.series, auto.step, auto.repeat) == ("LIN0", "3", 2)  # ambiguous: shortest layout wins
    assert (fixed.series, fixed.step, fixed.repeat) == ("LIN", "3", 2)


def test_two_digit_steps_detected_when_steps_exceed_nine():
    names = [f"LIN{s:02d}{r:02d}" for s in range(1, 12) for r in range(1, 4)]
    p = _parse(names)["LIN1103"]
    assert (p.series, p.step, p.repeat) == ("LIN", "11", 3)


def test_repeat_first_order():
    names = [f"S{r:02d}{s}" for s in "12n" for r in range(1, 4)]
    p = _parse(names, step_first=False, repeat_digits=2, step_digits=1)
    assert (p["S032"].series, p["S032"].step, p["S032"].repeat) == ("S", "2", 3)
    assert p["S01n"].role == Role.NEGATIVE


def test_delimited_names():
    p = _parse(["LoD_HPV16_neg_24", "LoD_HPV16_3_7", "LE-20-1-01", "Mix A 2 3"])
    assert (p["LoD_HPV16_neg_24"].series, p["LoD_HPV16_neg_24"].step, p["LoD_HPV16_neg_24"].repeat) == ("LoD_HPV16", NEG_STEP, 24)
    assert (p["LoD_HPV16_3_7"].series, p["LoD_HPV16_3_7"].step, p["LoD_HPV16_3_7"].repeat) == ("LoD_HPV16", "3", 7)
    assert (p["LE-20-1-01"].series, p["LE-20-1-01"].step, p["LE-20-1-01"].repeat) == ("LE-20", "1", 1)
    assert (p["Mix A 2 3"].series, p["Mix A 2 3"].step, p["Mix A 2 3"].repeat) == ("Mix A", "2", 3)


def test_delimited_repeat_first():
    p = _parse(["HPV_07_3"], step_first=False)["HPV_07_3"]
    assert (p.series, p.step, p.repeat) == ("HPV", "3", 7)


def test_fixed_digits_fall_back_when_last_token_holds_both_counters():
    p = _parse(["LE_20_101", "LE_20_102", "LE_20_201"], step_digits=1, repeat_digits=2)["LE_20_102"]
    assert (p.series, p.step, p.repeat) == ("LE_20", "1", 2)


def test_controls_and_unknown_names():
    config = NamingConfig()
    for name in ["(-) Ctrl", "NTC", "ntc 2", "NTC_3", "(+)  Ctrl"]:
        assert is_control_name(name, config), name
    assert not is_control_name("PC101", config)
    p = _parse(["NTC", "Blank sample", "PC101"])
    assert p["NTC"].role == Role.CONTROL
    assert p["Blank sample"].role == Role.UNKNOWN
    assert (p["PC101"].series, p["PC101"].step, p["PC101"].repeat) == ("PC", "1", 1)


def test_custom_negative_marker():
    p = _parse(["X101", "X102", "X201", "X202", "XN01", "XN02"], negative_markers=("N",))
    assert p["XN02"].role == Role.NEGATIVE
    assert p["XN02"].repeat == 2
