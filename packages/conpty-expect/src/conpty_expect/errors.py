from __future__ import annotations


class ConptyExpectError(Exception):
    pass


class TimeoutError(ConptyExpectError):
    pass


class EofError(ConptyExpectError):
    pass

