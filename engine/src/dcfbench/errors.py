"""Exceptions shared by the forecast rules and the engine."""


class PolicyNotSupported(NotImplementedError):
    """The policy asks for a rule that version zero does not implement."""


class ValuationError(ValueError):
    """The inputs and policy do not define a value (g at or above the rate, no debt for a coupon, ...)."""
