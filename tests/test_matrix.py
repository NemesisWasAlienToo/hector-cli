"""Unit tests for hector.core.expand_matrix."""

from hector.core import expand_matrix


def test_no_matrix_yields_single_empty_job():
    assert expand_matrix(None) == [{}]
    assert expand_matrix({}) == [{}]
    assert expand_matrix({"other": 1}) == [{}]   # no 'variables' key


def test_single_variable():
    jobs = expand_matrix({"variables": {"BOARD": ["a", "b"]}})
    assert jobs == [{"BOARD": "a"}, {"BOARD": "b"}]


def test_cartesian_product():
    jobs = expand_matrix({"variables": {"BOARD": ["a", "b"], "OPT": [0, 1]}})
    assert len(jobs) == 4
    assert {"BOARD": "a", "OPT": 0} in jobs
    assert {"BOARD": "b", "OPT": 1} in jobs


def test_exclude_rule_removes_combo():
    jobs = expand_matrix({
        "variables": {"BOARD": ["a", "b"], "OPT": [0, 1]},
        "exclude": [{"BOARD": "a", "OPT": 1}],
    })
    assert {"BOARD": "a", "OPT": 1} not in jobs
    assert len(jobs) == 3
