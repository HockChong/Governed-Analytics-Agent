"""Project exceptions. Expected request-path failures are exit codes, not these."""


class GovernedAnalyticsError(Exception):
    """Base class for every exception raised by project code."""


class SnapshotError(GovernedAnalyticsError):
    """The warehouse snapshot was refused or could not be verified."""


class MigrationError(GovernedAnalyticsError):
    """The migrations directory is malformed."""
