"""Pytest config for qgi-ml.

Registers the ``slow`` marker used by tests that exercise the PyMC NUTS
sampler in `tests/test_shape_prototype_fit.py`. Use ``pytest -m slow``
to run them, ``pytest -m "not slow"`` to skip.
"""


def pytest_configure(config):  # noqa: ANN001
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (e.g., PyMC NUTS sampling); skip with -m 'not slow'",
    )
