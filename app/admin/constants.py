from flask_babel import _

# 3 is unused
class ReportTypes:
    ALL = -1
    USER = 0
    POST = 1
    COMMENT = 2
    DM = 4

    @classmethod
    def get_choices(cls):
        return [
            (cls.ALL, _("All")),
            (cls.USER, _("User")),
            (cls.POST, _("Post")),
            (cls.COMMENT, _("Comment")),
            (cls.DM, _("Direct Message")),
        ]
