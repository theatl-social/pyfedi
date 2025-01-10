REQUEST_TIMEOUT = 2

POST_TYPE_LINK = 1
POST_TYPE_ARTICLE = 2
POST_TYPE_IMAGE = 3
POST_TYPE_VIDEO = 4
POST_TYPE_POLL = 5

DATETIME_MS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

# Community subscription levels
SUBSCRIPTION_OWNER = 3
SUBSCRIPTION_MODERATOR = 2
SUBSCRIPTION_MEMBER = 1
SUBSCRIPTION_NONMEMBER = 0
SUBSCRIPTION_PENDING = -1
SUBSCRIPTION_BANNED = -2

THREAD_CUTOFF_DEPTH = 4

REPORT_STATE_NEW = 0
REPORT_STATE_ESCALATED = 1
REPORT_STATE_APPEALED = 2
REPORT_STATE_RESOLVED = 3
REPORT_STATE_DISCARDED = -1

# different types of content notification that people can have. e.g. when a new post is made by a user or in a community.
# see NotificationSubscription in models.py
NOTIF_USER = 0
NOTIF_COMMUNITY = 1
NOTIF_TOPIC = 2
NOTIF_POST = 3
NOTIF_REPLY = 4

ROLE_STAFF = 3
ROLE_ADMIN = 4

DOWNVOTE_ACCEPT_ALL = 0
DOWNVOTE_ACCEPT_MEMBERS = 2
DOWNVOTE_ACCEPT_INSTANCE = 4
DOWNVOTE_ACCEPT_TRUSTED = 6

MICROBLOG_APPS = ["mastodon", "misskey", "akkoma", "iceshrimp", "pleroma"]

APLOG_IN            = True

APLOG_MONITOR       = (True, 'Debug this')

APLOG_SUCCESS       = (True, 'success')
APLOG_FAILURE       = (True, 'failure')
APLOG_IGNORED       = (True, 'ignored')
APLOG_PROCESSING    = (True, 'processing')

APLOG_NOTYPE        = (True, 'Unknown')
APLOG_DUPLICATE     = (True, 'Duplicate')
APLOG_FOLLOW        = (True, 'Follow')
APLOG_ACCEPT        = (True, 'Accept')
APLOG_DELETE        = (True, 'Delete')
APLOG_CHATMESSAGE   = (True, 'Create ChatMessage')
APLOG_CREATE        = (True, 'Create')
APLOG_UPDATE        = (True, 'Update')
APLOG_LIKE          = (True, 'Like')
APLOG_DISLIKE       = (True, 'Dislike')
APLOG_REPORT        = (True, 'Report')
APLOG_USERBAN       = (True, 'User Ban')
APLOG_LOCK          = (True, 'Post Lock')

APLOG_UNDO_FOLLOW   = (True, 'Undo Follow')
APLOG_UNDO_DELETE   = (True, 'Undo Delete')
APLOG_UNDO_VOTE     = (True, 'Undo Vote')
APLOG_UNDO_USERBAN  = (True, 'Undo User Ban')

APLOG_ADD           = (True, 'Add Mod/Sticky')
APLOG_REMOVE        = (True, 'Remove Mod/Sticky')

APLOG_ANNOUNCE      = (True, 'Announce')
APLOG_PT_VIEW       = (True, 'PeerTube View')
