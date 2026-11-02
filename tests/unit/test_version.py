import re

import trackie


def test_version_is_pep440() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+.*|0\+unknown", trackie.__version__)
