# Constants
ADD_TEXT, ADD_ANON, SELECT_VISIBILITY, SELECT_GROUP = range(4)
PRAY_TEXT, PRAY_AUDIO = range(10, 12)

# Group tracking
group_members = {}  # chat_id -> set of user_ids
user_groups = {}    # user_id -> set of chat_ids
group_titles = {}