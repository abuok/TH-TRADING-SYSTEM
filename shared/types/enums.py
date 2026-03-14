from enum import Enum


class SessionState(str, Enum):
    PRE_SESSION = "PRE_SESSION"
    LONDON_OPEN = "LONDON_OPEN"
    LONDON_MID = "LONDON_MID"
    NY_OPEN = "NY_OPEN"
    POST_SESSION = "POST_SESSION"
    ASIA_SESSION = "ASIA_SESSION"
    OUT_OF_SESSION = "OUT_OF_SESSION"


class BiasState(str, Enum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    NEUTRAL = "NEUTRAL"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class AlignmentState(str, Enum):
    ALIGNED = "ALIGNED"
    UNALIGNED = "UNALIGNED"


class LockoutState(str, Enum):
    TRADEABLE = "TRADEABLE"
    SOFT_LOCK = "SOFT_LOCK"
    HARD_LOCK = "HARD_LOCK"


class TicketState(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PROCESSED = "PROCESSED"
    REJECTED_BROKER = "REJECTED_BROKER"
    REJECTED_JIT = "REJECTED_JIT"
    EXPIRED = "EXPIRED"


class PHXStage(str, Enum):
    IDLE = "IDLE"
    BIAS = "BIAS"
    SWEEP = "SWEEP"
    DISPLACE = "DISPLACE"
    CHOCH_BOS = "CHOCH_BOS"
    RETEST = "RETEST"
    TRIGGER = "TRIGGER"
