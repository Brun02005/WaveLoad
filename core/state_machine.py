from enum import Enum

class DownloadState(Enum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    DOWNLOADING = "DOWNLOADING"
    POST_PROCESSING = "POST_PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"

    @property
    def is_terminal(self) -> bool:
        return self in (DownloadState.COMPLETED, DownloadState.FAILED, DownloadState.CANCELLED)

    @property
    def is_active(self) -> bool:
        return self in (
            DownloadState.PREPARING, 
            DownloadState.DOWNLOADING, 
            DownloadState.POST_PROCESSING, 
            DownloadState.RETRYING
        )

class StateTransitionError(Exception):
    pass

class StateMachine:
    """Validates state transitions for a download item."""
    
    # Define valid transitions from each state
    _VALID_TRANSITIONS = {
        DownloadState.QUEUED: {DownloadState.PREPARING, DownloadState.DOWNLOADING, DownloadState.CANCELLED, DownloadState.PAUSED},
        DownloadState.PREPARING: {DownloadState.DOWNLOADING, DownloadState.FAILED, DownloadState.CANCELLED},
        DownloadState.DOWNLOADING: {DownloadState.POST_PROCESSING, DownloadState.FAILED, DownloadState.CANCELLED, DownloadState.PAUSED},
        DownloadState.POST_PROCESSING: {DownloadState.COMPLETED, DownloadState.FAILED, DownloadState.CANCELLED},
        DownloadState.FAILED: {DownloadState.RETRYING, DownloadState.CANCELLED, DownloadState.QUEUED},
        DownloadState.RETRYING: {DownloadState.PREPARING, DownloadState.CANCELLED, DownloadState.FAILED},
        DownloadState.CANCELLED: {DownloadState.QUEUED}, # Can be restarted
        DownloadState.PAUSED: {DownloadState.QUEUED, DownloadState.DOWNLOADING, DownloadState.CANCELLED},
        DownloadState.COMPLETED: set(), # Terminal state, cannot transition elsewhere
    }

    @classmethod
    def can_transition(cls, current: DownloadState, target: DownloadState) -> bool:
        """Check if a transition is valid."""
        return target in cls._VALID_TRANSITIONS.get(current, set())

    @classmethod
    def validate_transition(cls, current: DownloadState, target: DownloadState):
        """Raise an error if the transition is invalid."""
        if not cls.can_transition(current, target):
            raise StateTransitionError(f"Invalid state transition from {current.name} to {target.name}")
