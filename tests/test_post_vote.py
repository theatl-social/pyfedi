"""
Tests for Post.vote() score bookkeeping.

Post.score should always reflect the votes that currently exist. In particular, casting a vote and then
undoing / reversing / switching it must not leave the score drifted away from where it started.

The database, redis and user lookups are mocked so these tests don't modify any data.
"""
import os
import sys
from datetime import timedelta
from unittest.mock import MagicMock, PropertyMock, patch

# Allow running this file directly (python tests/test_post_vote.py) by putting the project root on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from flask import Flask

from app import db
from app.models import Post, PostVote, utcnow


# Values in use on production at the time these tests were written. With the default (1.0) the spicy boost does nothing.
SPICY_CONFIG = {'SPICY_UNDER_10': 2.5, 'SPICY_UNDER_30': 1.85, 'SPICY_UNDER_60': 1.25}
NOT_SPICY_CONFIG = {'SPICY_UNDER_10': 1.0, 'SPICY_UNDER_30': 1.0, 'SPICY_UNDER_60': 1.0}


class FakeVoteStore:
    """Stands in for the post_vote table: PostVote.query.filter_by(...).first(), db.session.add() and db.session.delete()"""
    def __init__(self):
        self.votes = {}     # (user_id, post_id) -> PostVote

    def filter_by(self, user_id, post_id):
        result = MagicMock()
        result.first.return_value = self.votes.get((user_id, post_id))
        return result

    def add(self, obj):
        if isinstance(obj, PostVote):
            self.votes[(obj.user_id, obj.post_id)] = obj

    def delete(self, obj):
        if isinstance(obj, PostVote):
            self.votes.pop((obj.user_id, obj.post_id), None)


def make_app(spicy_config):
    app = Flask(__name__)
    app.config.update(spicy_config)
    return app


@pytest.fixture
def voting(request):
    """Yields a function that builds a post with the given number of existing up/down votes, with all external
    dependencies of Post.vote() mocked. Use @pytest.mark.parametrize('voting', [...], indirect=True) to choose
    the SPICY_* config; defaults to SPICY_CONFIG."""
    spicy_config = getattr(request, 'param', SPICY_CONFIG)
    app = make_app(spicy_config)
    store = FakeVoteStore()

    session = MagicMock()
    session.add.side_effect = store.add
    session.delete.side_effect = store.delete

    author = MagicMock()
    author.id = 999
    author.has_blocked_user.return_value = False
    author.has_blocked_instance.return_value = False

    community = MagicMock()
    community.low_quality = False
    community.scale_by.return_value = 0

    with app.app_context(), \
            patch('app.redis_client', MagicMock()), \
            patch.object(db, 'session', session), \
            patch.object(PostVote, 'query', store), \
            patch.object(Post, 'author', new_callable=PropertyMock, return_value=author), \
            patch.object(Post, 'community', new_callable=PropertyMock, return_value=community), \
            patch('app.models.votes_cast_today', return_value=0):

        def build_post(up_votes=0, down_votes=0):
            created = utcnow() - timedelta(hours=1)
            return Post(id=1, user_id=author.id, up_votes=up_votes, down_votes=down_votes,
                        score=up_votes - down_votes, reply_count=0, created_at=created, posted_at=created)

        yield build_post


def make_voter(user_id=1):
    user = MagicMock()
    user.id = user_id
    user.instance_id = 1
    user.is_local.return_value = False     # skip last_seen / cache invalidation
    return user


# Number of existing votes on the post, chosen to hit each SPICY_* band, plus one band with no amplification.
VOTE_COUNT_BANDS = [0, 5, 20, 45, 100]


@pytest.mark.parametrize('existing_votes', VOTE_COUNT_BANDS)
def test_upvote_then_undo_restores_score(voting, existing_votes):
    post = voting(up_votes=existing_votes)
    start = post.score
    voter = make_voter()

    post.vote(voter, 'upvote', None)
    post.vote(voter, 'upvote', None)    # same direction again = undo

    assert post.up_votes == existing_votes
    assert post.score == start


@pytest.mark.parametrize('existing_votes', VOTE_COUNT_BANDS)
def test_upvote_then_reversal_restores_score(voting, existing_votes):
    post = voting(up_votes=existing_votes)
    start = post.score
    voter = make_voter()

    post.vote(voter, 'upvote', None)
    post.vote(voter, 'reversal', None)  # what the API sends for score = 0

    assert post.up_votes == existing_votes
    assert post.score == start


@pytest.mark.parametrize('existing_votes', VOTE_COUNT_BANDS)
def test_downvote_then_undo_restores_score(voting, existing_votes):
    post = voting(up_votes=existing_votes)
    start = post.score
    voter = make_voter()

    post.vote(voter, 'downvote', None)
    post.vote(voter, 'downvote', None)

    assert post.down_votes == 0
    assert post.score == start


@pytest.mark.parametrize('existing_votes', VOTE_COUNT_BANDS)
def test_downvote_then_reversal_restores_score(voting, existing_votes):
    post = voting(up_votes=existing_votes)
    start = post.score
    voter = make_voter()

    post.vote(voter, 'downvote', None)
    post.vote(voter, 'reversal', None)

    assert post.down_votes == 0
    assert post.score == start


@pytest.mark.parametrize('existing_votes', VOTE_COUNT_BANDS)
def test_upvote_switch_to_downvote_then_undo_restores_score(voting, existing_votes):
    post = voting(up_votes=existing_votes)
    start = post.score
    voter = make_voter()

    post.vote(voter, 'upvote', None)
    post.vote(voter, 'downvote', None)  # switch
    post.vote(voter, 'downvote', None)  # undo

    assert post.up_votes == existing_votes
    assert post.down_votes == 0
    assert post.score == start


@pytest.mark.parametrize('existing_votes', VOTE_COUNT_BANDS)
def test_downvote_switch_to_upvote_then_undo_restores_score(voting, existing_votes):
    post = voting(up_votes=existing_votes)
    start = post.score
    voter = make_voter()

    post.vote(voter, 'downvote', None)
    post.vote(voter, 'upvote', None)    # switch
    post.vote(voter, 'upvote', None)    # undo

    assert post.up_votes == existing_votes
    assert post.down_votes == 0
    assert post.score == start


@pytest.mark.parametrize('existing_votes', VOTE_COUNT_BANDS)
def test_upvote_switch_to_downvote_scores_like_a_downvote(voting, existing_votes):
    """Switching from up to down should leave the post scoring below where it started, as a plain downvote would."""
    post = voting(up_votes=existing_votes)
    start = post.score
    voter = make_voter()

    post.vote(voter, 'upvote', None)
    post.vote(voter, 'downvote', None)

    assert post.up_votes == existing_votes
    assert post.down_votes == 1
    assert post.score < start


def test_repeated_toggling_does_not_inflate_score(voting):
    """One user toggling their upvote over and over must not change the score. """
    post = voting(up_votes=5)
    start = post.score
    voter = make_voter()

    for _ in range(1000):
        post.vote(voter, 'upvote', None)
        post.vote(voter, 'upvote', None)

    assert post.up_votes == 5
    assert post.score == start


def test_many_users_voting_then_undoing_restores_score(voting):
    """Votes cast while the post is in a spicy band and undone after it has left that band must still net to zero."""
    post = voting(up_votes=0)
    voters = [make_voter(user_id) for user_id in range(1, 81)]

    for voter in voters:
        post.vote(voter, 'upvote', None)
    for voter in voters:
        post.vote(voter, 'upvote', None)

    assert post.up_votes == 0
    assert post.score == 0


@pytest.mark.parametrize('voting', [NOT_SPICY_CONFIG], indirect=True)
@pytest.mark.parametrize('existing_votes', VOTE_COUNT_BANDS)
def test_toggling_without_spicy_multipliers_restores_score(voting, existing_votes):
    """Control: with all SPICY_* settings at 1.0 every cycle should already net to zero."""
    post = voting(up_votes=existing_votes)
    start = post.score
    voter = make_voter()

    post.vote(voter, 'upvote', None)
    post.vote(voter, 'upvote', None)
    post.vote(voter, 'downvote', None)
    post.vote(voter, 'reversal', None)
    post.vote(voter, 'upvote', None)
    post.vote(voter, 'downvote', None)
    post.vote(voter, 'downvote', None)

    assert post.up_votes == existing_votes
    assert post.down_votes == 0
    assert post.score == start


def test_score_is_plain_net_votes(voting):
    """The spicy boost belongs in ranking only, score should be up_votes - down_votes."""
    post = voting()
    for user_id in range(1, 41):
        post.vote(make_voter(user_id), 'upvote', None)
    for user_id in range(41, 51):
        post.vote(make_voter(user_id), 'downvote', None)

    assert post.up_votes == 40
    assert post.down_votes == 10
    assert post.score == 30


def test_early_upvotes_boost_ranking(voting):
    post = voting()
    post.vote(make_voter(), 'upvote', None)

    unboosted = post.post_ranking(post.score + post.reply_count, post.created_at)
    assert post.ranking > unboosted


@pytest.mark.parametrize('existing_votes', VOTE_COUNT_BANDS)
def test_ranking_restored_after_vote_undone(voting, existing_votes):
    post = voting(up_votes=existing_votes)
    voter = make_voter()

    post.vote(voter, 'upvote', None)
    post.vote(voter, 'downvote', None)
    ranking_after_downvote = post.ranking
    post.vote(voter, 'upvote', None)
    post.vote(voter, 'upvote', None)
    post.vote(voter, 'downvote', None)

    assert post.ranking == ranking_after_downvote


def test_spicy_score_matches_previous_boost_for_upvotes(voting):
    """For a post that has only received upvotes, the derived boost equals what the old code accumulated vote by vote."""
    for up_votes in range(0, 101):
        post = voting(up_votes=up_votes)
        accumulated = 0.0
        for votes_before in range(up_votes):
            if votes_before <= 10:
                accumulated += SPICY_CONFIG['SPICY_UNDER_10']
            elif votes_before <= 30:
                accumulated += SPICY_CONFIG['SPICY_UNDER_30']
            elif votes_before <= 60:
                accumulated += SPICY_CONFIG['SPICY_UNDER_60']
            else:
                accumulated += 1
        assert post.spicy_score() == pytest.approx(accumulated)


@pytest.mark.parametrize('voting', [NOT_SPICY_CONFIG], indirect=True)
def test_spicy_score_without_multipliers_is_score(voting):
    post = voting(up_votes=7, down_votes=3)
    assert post.spicy_score() == post.score


if __name__ == '__main__':
    pytest.main([__file__])
