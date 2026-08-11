"""
Service layer.

Business operations live here, not in controllers. Services own transactions,
validation and audit writes, and re-check authorisation themselves so a
controller that forgets a decorator still cannot mutate another tenant's data.
"""
