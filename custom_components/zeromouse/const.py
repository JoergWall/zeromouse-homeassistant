"""Constants for the ZeroMOUSE integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "zeromouse"
MANUFACTURER = "ZeroMOUSE"

# Backend (AWS Amplify, extracted from the official app bundle)
REGION = "eu-central-1"
USER_POOL_ID = "eu-central-1_LS6CKN0t1"
USER_POOL_CLIENT_ID = "7pdec0rbivg5hg8u3pke4veg0f"
IDENTITY_POOL_ID = "eu-central-1:2b2f7d40-d6f9-474e-a06b-6441c4059601"
GRAPHQL_HOST = "f36gc6o7jnewxe37dhn3fochza.appsync-api.eu-central-1.amazonaws.com"
GRAPHQL_URL = f"https://{GRAPHQL_HOST}/graphql"
REALTIME_URL = (
    "wss://f36gc6o7jnewxe37dhn3fochza.appsync-realtime-api.eu-central-1.amazonaws.com"
    "/graphql"
)
REST_BASE_URL = "https://4oj9bcxedi.execute-api.eu-central-1.amazonaws.com/DEV"
IMAGE_BUCKET = "mbr-ptf-images-eu-central-1-dev"

UPDATE_INTERVAL = timedelta(seconds=60)
STATISTICS_INTERVAL = timedelta(minutes=30)
EVENT_LIMIT = 20

EVENT_ZEROMOUSE = "zeromouse_event"

# Shadow: state.{reported,desired}.system.kkzmBlockModeIn
ENTRY_MODES: dict[int, str] = {
    0: "free_entry",
    1: "blocking_prey",
    2: "face_detection",
    3: "locked",
}
# Shadow: state.{reported,desired}.system.kkzmBlockModeOut
EXIT_MODES: dict[int, str] = {
    0: "open",
    1: "locked",
    2: "time_based",
}
# Shadow: state.{reported,desired}.system.undecidableMode
UNDECIDABLE_MODES: dict[int, str] = {
    0: "smart",
    1: "always_allow",
    2: "always_block",
}
# Shadow: state.{reported,desired}.proximity.irPreyEventTime (seconds)
PREY_BLOCK_TIMES: list[int] = [10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]

# Minutes after midnight, defaults used by the app
DEFAULT_OUT_OPEN_AT = 540
DEFAULT_OUT_CLOSE_AT = 1080

# Event.classification_byNet
CLASSIFICATIONS: list[str] = [
    "prey",
    "clean",
    "undecidable",
    "out",
    "hand",
    "early",
    "late",
    "free",
    "test",
    "unknown",
]

# The app shows and filters events in five groups (app 1.14.19, filter dialog
# and event titles). Everything else counts as "undecidable" there.
CLASSIFICATION_GROUPS: dict[str, frozenset[str]] = {
    "clean": frozenset({"clean", "early"}),  # Keine Beute erkannt
    "prey": frozenset({"prey"}),  # Beute erkannt
    "undecidable": frozenset({"undecidable", "late", "unknown"}),  # Nicht entscheidbar
    "hand": frozenset({"test", "hand"}),  # Hand erkannt
    "out": frozenset({"out"}),  # Rausgehen erkannt
}


def classification_group(classification: object) -> str:
    """Return the app's group of a raw classification."""
    for group, members in CLASSIFICATION_GROUPS.items():
        if classification in members:
            return group
    return "undecidable"
