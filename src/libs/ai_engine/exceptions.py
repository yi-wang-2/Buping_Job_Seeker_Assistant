class AIEngineError(Exception):
    """Base exception for the unified AI engine."""


class ProviderConfigurationError(AIEngineError):
    """Raised when a provider cannot be configured safely."""


class ProviderInvocationError(AIEngineError):
    """Raised when a provider invocation fails after bounded retries."""


class ContextBudgetError(AIEngineError):
    """Raised when protected context cannot fit in the available budget."""

