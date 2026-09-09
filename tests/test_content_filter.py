import unittest
from app.models import Post


class TestContentFilter(unittest.TestCase):

    content_filters = {'trump': ['trump'],
                       'elon': ['elon', 'musk']}

    def test_content_filter_basic(self):
        p = Post(title="Trump does something daft again", user_id=1)
        filtered = p.blocked_by_content_filter(self.content_filters, 2)
        assert filtered

    def test_content_filter_basic_same_author(self):
        p = Post(title="Trump does something daft again", user_id=1)
        filtered = p.blocked_by_content_filter(self.content_filters, 1)
        assert not filtered

    def test_content_filter_basic_not(self):
        p = Post(title="Turnip does something daft again", user_id=1)
        filtered = p.blocked_by_content_filter(self.content_filters, 2)
        assert not filtered

    def test_content_filter_square_brackets(self):
        p = Post(title="[Trump] does something daft again", user_id=1)
        filtered = p.blocked_by_content_filter(self.content_filters, 2)
        assert filtered


    def test_content_filter_square_bracket_filter(self):
        # Upstream built this local filter and then passed self.content_filters,
        # making the test a duplicate of test_content_filter_square_brackets and
        # never exercising a bracketed filter *pattern*.
        content_filters = {'trump': ['[Trump]'],
                           'elon': ['elon', 'musk']}
        p = Post(title="[Trump] does something daft again", user_id=1)
        filtered = p.blocked_by_content_filter(content_filters, 2)
        assert filtered



    def test_content_filter_punctuated_keywords(self):
        """Filters carrying punctuation must still match.

        The title is tokenized with \\w+, so a keyword containing any
        non-word character can never equal a token. Before this was fixed,
        every such filter failed open -- the user saw exactly the content
        they had asked to hide.
        """
        cases = [
            ({'ai': ['c++']}, 'Why c++ is still everywhere'),
            ({'virus': ['covid-19']}, 'New covid-19 numbers released'),
            ({'politics': ['u.s.']}, 'The u.s. votes again'),
            ({'trump': ['[trump]']}, '[Trump] does something daft again'),
        ]
        for content_filters, title in cases:
            with self.subTest(title=title):
                p = Post(title=title, user_id=1)
                assert p.blocked_by_content_filter(content_filters, 2)

    def test_content_filter_single_word_still_token_matched(self):
        """Single-word filters keep token semantics: no substring matches."""
        p = Post(title="I ate a melon for breakfast", user_id=1)
        assert not p.blocked_by_content_filter({'elon': ['elon']}, 2)


if __name__ == '__main__':
    unittest.main()