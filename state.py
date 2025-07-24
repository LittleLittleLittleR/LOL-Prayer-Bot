from dataclasses import dataclass

# Constants
ADD_TEXT, ADD_ANON = range(2)
PRAY_TEXT, PRAY_AUDIO = range(10, 12)

@dataclass
class PrayerRequest:
    id: str
    user_id: int
    username: str
    text: str
    is_anonymous: bool