import unittest
from unittest.mock import Mock

from app.models import Post


class TestYoutubeEmbed(unittest.TestCase):

    def test_video_embed(self):
        """Test basic YouTube video embed"""
        post = Mock()
        post.url = 'https://www.youtube.com/watch?v=t08dDBjzudQ'

        result = Post.youtube_embed(post)
        self.assertEqual(result, 't08dDBjzudQ?rel=0')

    def test_playlist_embed(self):
        """Test YouTube playlist embed"""
        post = Mock()
        post.url = 'https://www.youtube.com/playlist?list=OLAK5uy_m0ymBxrjfVeJeuv9sde3pN_yvAfwWuxGw'

        result = Post.youtube_embed(post)
        self.assertEqual(result, 'videoseries?list=OLAK5uy_m0ymBxrjfVeJeuv9sde3pN_yvAfwWuxGw')

    def test_shorts_embed(self):
        """Test YouTube shorts embed"""
        post = Mock()
        post.url = 'https://www.youtube.com/shorts/abc123'

        result = Post.youtube_embed(post)
        self.assertEqual(result, 'abc123?rel=0')

    def test_empty_url(self):
        """Test with no URL"""
        post = Mock()
        post.url = None

        result = Post.youtube_embed(post)
        self.assertEqual(result, '')
