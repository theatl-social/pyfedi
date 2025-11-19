import unittest
from unittest.mock import patch

from app.utils import dedupe_post_ids


class TestDudupePostIds(unittest.TestCase):

    @patch('app.utils.low_value_reposters')
    def test_basic_dedupe(self, mock_low_value):
        """Test basic dedupe with no cross-posts"""
        mock_low_value.return_value = set()
        params = [(1, None, 1, 10), (2, None, 1, 10)]
        result = dedupe_post_ids(params, limit_to_visible=False)
        self.assertEqual(result, [1, 2])

    @patch('app.utils.low_value_reposters')
    def test_empty_input(self, mock_low_value):
        """Test with empty input"""
        mock_low_value.return_value = set()
        result = dedupe_post_ids([], limit_to_visible=False)
        self.assertEqual(result, [])
        
        result = dedupe_post_ids(None, limit_to_visible=False)
        self.assertEqual(result, [])

    @patch('app.utils.low_value_reposters')
    def test_regular_cross_posts(self, mock_low_value):
        """Test cross-posts from regular (non-bot) users - highest reply count wins"""
        mock_low_value.return_value = set()  # No bots

        params = [
            (1, [2, 3], 100, 5),  # Original post (5 replies)
            (2, [1, 3], 101, 10), # Cross-post 1 (10 replies)
            (3, [1, 2], 102, 15)  # Cross-post 2 (15 replies) - should win
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        self.assertEqual(result, [3])  # Post with most replies should win

    @patch('app.utils.low_value_reposters')
    def test_low_value_reposter_cross_posts(self, mock_low_value):
        """Test cross-posts from bots - non-bot with highest reply count wins"""
        mock_low_value.return_value = {100}  # User 100 is a bot

        params = [
            (1, [2, 3], 100, 5),  # Bot post (5 replies) - should be replaced
            (2, [1, 3], 101, 10), # Non-bot cross-post 1 (10 replies)
            (3, [1, 2], 102, 15)  # Non-bot cross-post 2 (15 replies) - should win
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        self.assertEqual(result, [3])  # Non-bot post with most replies should win

    @patch('app.utils.low_value_reposters')
    def test_mixed_scenarios(self, mock_low_value):
        """Test mix of regular posts, cross-posts, and low-value reposters"""
        mock_low_value.return_value = {200}

        params = [
            (1, None, 100, 5),     # Regular post, no cross-posts
            (2, [3, 4], 101, 8),   # Regular user with cross-posts (8 replies)
            (3, [2, 4], 102, 12),  # Cross-post of above (12 replies) - should win
            (4, [2, 3], 103, 6),   # Cross-post of above (6 replies)
            (5, [6, 7], 200, 3),   # Low-value reposter (3 replies)
            (6, [5, 7], 201, 20),  # Cross-post 1 (20 replies) - should win
            (7, [5, 6], 202, 15)   # Cross-post 2 (15 replies)
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        self.assertEqual(result, [1, 3, 6])  # Regular post, best from first group (12 replies), best from second group (20 replies)

    @patch('app.utils.low_value_reposters')
    def test_no_cross_posts_found(self, mock_low_value):
        """Test when cross-post IDs don't match actual posts"""
        mock_low_value.return_value = {100}

        params = [
            (1, [99], 100, 5),  # Cross-post ID 99 doesn't exist in params, but post 1 is in visible list
            (2, None, 101, 10)
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        # Post 1 should remain because cross-post 99 doesn't exist in the dataset
        # So all_related_posts will be [1, 99], and after filtering to only those in post_ids, only 1 remains
        self.assertEqual(result, [1, 2])  # Both posts should remain

    @patch('app.utils.low_value_reposters')
    def test_priority_prevents_filtering(self, mock_low_value):
        """Test that prioritized posts don't get filtered by later posts"""
        mock_low_value.return_value = {100}
        
        params = [
            (1, [2], 100, 5),    # Low-value reposter, prioritizes post 2
            (2, [1], 101, 10),   # Should be kept (prioritized)
            (3, [2], 102, 15)    # Should not filter out post 2 since it's prioritized
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        self.assertEqual(result, [2, 3])  # Both 2 and 3 should remain

    @patch('app.utils.low_value_reposters')
    def test_performance_with_1000_posts(self, mock_low_value):
        """Test performance with 1000 posts including cross-posts and low-value reposters"""
        import time
        
        # Set up some low-value reposters
        low_value_users = {user_id for user_id in range(900, 910)}  # 10 low-value users
        mock_low_value.return_value = low_value_users
        
        # Generate 1000 posts with realistic cross-post references
        params = []
        for i in range(1, 1001):
            post_id = i
            user_id = 100 + (i % 50)  # 50 different users
            reply_count = i % 100  # Reply counts 0-99
            
            # Create cross-posts that reference other posts in the same dataset
            cross_posts = None
            if i % 10 == 0 and i <= 900:  # Every 10th post has cross-posts, but only up to 900 to avoid out-of-range
                # Create 2-3 cross-posts that reference posts within our 1000 post range
                cross_posts = [i + 50, i + 100]  # Reference posts 50 and 100 positions ahead
                if i % 20 == 0 and i <= 800:  # Some have 3 cross-posts
                    cross_posts.append(i + 150)
            
            # Some users are low-value reposters
            if user_id in low_value_users:
                user_id = 900 + (i % 10)  # Map to low-value users
            
            params.append((post_id, cross_posts, user_id, reply_count))
        
        # Time the execution
        start_time = time.time()
        result = dedupe_post_ids(params, limit_to_visible=False)
        end_time = time.time()
        
        execution_time = end_time - start_time
        print(f"\\nPerformance test: {len(params)} posts processed in {execution_time:.4f} seconds")
        print(f"Result: {len(result)} posts after deduplication")
        print(f"Deduplication ratio: {len(result)/len(params):.2%}")
        
        # Should complete reasonably quickly (under 1 second for 1000 posts)
        self.assertLess(execution_time, 1.0, "Function should complete within 1 second for 1000 posts")
        self.assertGreater(len(result), 0, "Should return some posts")
        self.assertLess(len(result), 1000, "Should deduplicate some posts")

    @patch('app.utils.low_value_reposters')
    def test_worst_case_performance(self, mock_low_value):
        """Test worst-case performance: many low-value reposters with many cross-posts"""
        import time
        
        # Make half the users low-value reposters to trigger more nested loops
        low_value_users = {user_id for user_id in range(100, 150)}  # 50 low-value users
        mock_low_value.return_value = low_value_users
        
        # Generate 1000 posts where many are from low-value reposters with cross-posts
        params = []
        for i in range(1, 1001):
            post_id = i
            user_id = 100 + (i % 100)  # 100 different users, half are low-value
            reply_count = i % 100  # Reply counts 0-99
            
            # Give every low-value reposter cross-posts to trigger nested loop
            cross_posts = None
            if user_id in low_value_users and i <= 900:
                # Each low-value post has 3-5 cross-posts that exist in our dataset
                cross_posts = [i + 10, i + 20, i + 30]
                if i <= 800:
                    cross_posts.extend([i + 40, i + 50])
            elif i % 5 == 0 and i <= 950:  # Regular users also have some cross-posts
                cross_posts = [i + 25, i + 35]
            
            params.append((post_id, cross_posts, user_id, reply_count))
        
        # Time the execution
        start_time = time.time()
        result = dedupe_post_ids(params, limit_to_visible=False)
        end_time = time.time()
        
        execution_time = end_time - start_time
        print(f"\\nWorst-case test: {len(params)} posts processed in {execution_time:.4f} seconds")
        print(f"Result: {len(result)} posts after deduplication")
        print(f"Deduplication ratio: {len(result)/len(params):.2%}")
        
        # Even in worst case, should complete in reasonable time
        self.assertLess(execution_time, 2.0, "Function should complete within 2 seconds even in worst case")
        self.assertGreater(len(result), 0, "Should return some posts")
        self.assertLess(len(result), 1000, "Should deduplicate some posts")

    # Tests for is_all_view=False behavior
    @patch('app.utils.low_value_reposters')
    def test_basic_dedupe_not_all_view(self, mock_low_value):
        """Test basic dedupe with no cross-posts when is_all_view=False"""
        mock_low_value.return_value = set()
        params = [(1, None, 1, 10), (2, None, 1, 10)]
        result = dedupe_post_ids(params, limit_to_visible=True)
        self.assertEqual(result, [1, 2])

    @patch('app.utils.low_value_reposters')
    def test_regular_cross_posts_not_all_view(self, mock_low_value):
        """Test cross-posts from regular users when limit_to_visible=True - highest reply count wins"""
        mock_low_value.return_value = set()

        params = [
            (1, [2, 3], 100, 5),  # Original post (5 replies)
            (2, [1, 3], 101, 10), # Cross-post 1 (10 replies)
            (3, [1, 2], 102, 15)  # Cross-post 2 (15 replies) - should win
        ]
        result = dedupe_post_ids(params, limit_to_visible=True)
        self.assertEqual(result, [3])  # Post with most replies should win

    @patch('app.utils.low_value_reposters')
    def test_low_value_reposter_ignored_not_all_view(self, mock_low_value):
        """Test that low-value reposter logic still works when limit_to_visible=True if alternatives are visible"""
        mock_low_value.return_value = {100}  # User 100 is low-value
        
        params = [
            (1, [2, 3], 100, 5),  # Low-value reposter post (would normally be deprioritized)
            (2, [1, 3], 101, 10), # Cross-post 1 (10 replies)
            (3, [1, 2], 102, 15)  # Cross-post 2 (15 replies) - should win since it's visible and has most replies
        ]
        result = dedupe_post_ids(params, limit_to_visible=True)
        self.assertEqual(result, [3])  # Post 3 should win because alternatives are visible and it has most replies

    @patch('app.utils.low_value_reposters')
    def test_mixed_scenarios_not_all_view(self, mock_low_value):
        """Test mix of scenarios when limit_to_visible=True - highest reply count wins in each group"""
        mock_low_value.return_value = {200}

        params = [
            (1, None, 100, 5),     # Regular post, no cross-posts
            (2, [3, 4], 101, 8),   # Regular user with cross-posts (8 replies)
            (3, [2, 4], 102, 12),  # Cross-post of above (12 replies) - should win
            (4, [2, 3], 103, 6),   # Cross-post of above (6 replies)
            (5, [6, 7], 200, 3),   # Low-value reposter (3 replies)
            (6, [5, 7], 201, 20),  # Cross-post 1 (20 replies) - should win since it's visible and has most replies
            (7, [5, 6], 202, 15)   # Cross-post 2 (15 replies)
        ]
        result = dedupe_post_ids(params, limit_to_visible=True)
        # Regular post, best from first group (12 replies), best from second group (20 replies)
        self.assertEqual(result, [1, 3, 6])

    # Tests for limit_to_visible behavior specifically
    @patch('app.utils.low_value_reposters')
    def test_limit_to_visible_true_with_invisible_alternatives(self, mock_low_value):
        """Test that when limit_to_visible=True, invisible alternatives are not chosen"""
        mock_low_value.return_value = {100}  # User 100 is low-value
        
        params = [
            (1, [2, 3], 100, 5),  # Low-value reposter post, cross-posts 2,3 not in visible list
            (4, None, 101, 10),   # Regular post
        ]
        result = dedupe_post_ids(params, limit_to_visible=True)
        # Post 1 should remain because alternatives 2,3 are not visible
        self.assertEqual(result, [1, 4])

    @patch('app.utils.low_value_reposters')
    def test_limit_to_visible_true_with_visible_alternatives(self, mock_low_value):
        """Test that when limit_to_visible=True, visible alternatives are chosen"""
        mock_low_value.return_value = {100}  # User 100 is low-value
        
        params = [
            (1, [2, 3], 100, 5),  # Low-value reposter post
            (2, [1, 3], 101, 10), # Cross-post 1 (10 replies) - visible
            (3, [1, 2], 102, 15), # Cross-post 2 (15 replies) - visible, should win
        ]
        result = dedupe_post_ids(params, limit_to_visible=True)
        # Post 3 should win because it has most replies and is visible
        self.assertEqual(result, [3])

    @patch('app.utils.low_value_reposters')
    def test_limit_to_visible_false_with_invisible_alternatives(self, mock_low_value):
        """Test that when limit_to_visible=False, invisible alternatives are considered"""
        mock_low_value.return_value = {100}  # User 100 is low-value

        params = [
            (1, [99, 98], 100, 5),  # Low-value reposter post, cross-posts 99,98 not in visible list
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        # When limit_to_visible=False, we consider all related posts (1, 99, 98)
        # But only post 1 actually exists in the dataset, so it wins by default
        # Since cross-posts 99 and 98 don't exist in post_ids, post 1 remains
        self.assertEqual(result, [1])

    @patch('app.utils.low_value_reposters')
    def test_limit_to_visible_mixed_visibility(self, mock_low_value):
        """Test mix of visible and invisible alternatives with limit_to_visible=True"""
        mock_low_value.return_value = {100}

        params = [
            (1, [2, 99], 100, 5),  # Low-value reposter, cross-post 2 visible, 99 invisible
            (2, [1, 99], 101, 20), # Cross-post with 20 replies (visible)
        ]
        result = dedupe_post_ids(params, limit_to_visible=True)
        # Should choose post 2 since it's visible and has more replies
        self.assertEqual(result, [2])

    # Tests demonstrating the bug where non-bot users' posts are chosen regardless of reply count
    @patch('app.utils.low_value_reposters')
    def test_bug_non_bot_ignores_reply_count(self, mock_low_value):
        """BUG: Non-bot user posts are chosen first, ignoring reply counts"""
        mock_low_value.return_value = set()  # No low-value reposters

        params = [
            (1, [2, 3], 100, 5),  # Regular user post with 5 replies (encountered first)
            (2, [1, 3], 101, 50), # Cross-post with 50 replies - SHOULD win but doesn't
            (3, [1, 2], 102, 100) # Cross-post with 100 replies - SHOULD win but doesn't
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        # BUG: Current behavior returns [1] (first post wins)
        # EXPECTED: Should return [3] (post with most replies should win)
        self.assertEqual(result, [3], "Post with most replies should be chosen, not first encountered")

    @patch('app.utils.low_value_reposters')
    def test_bug_non_bot_ignores_reply_count_limit_visible(self, mock_low_value):
        """BUG: Non-bot user posts are chosen first even with limit_to_visible=True"""
        mock_low_value.return_value = set()  # No low-value reposters

        params = [
            (1, [2, 3], 100, 10), # Regular user post with 10 replies (encountered first)
            (2, [1, 3], 101, 75), # Cross-post with 75 replies - SHOULD win but doesn't
            (3, [1, 2], 102, 150) # Cross-post with 150 replies - SHOULD win but doesn't
        ]
        result = dedupe_post_ids(params, limit_to_visible=True)
        # BUG: Current behavior returns [1] (first post wins)
        # EXPECTED: Should return [3] (post with most replies should win)
        self.assertEqual(result, [3], "Post with most replies should be chosen even when limit_to_visible=True")

    @patch('app.utils.low_value_reposters')
    def test_bug_multiple_cross_post_groups_non_bot(self, mock_low_value):
        """BUG: Multiple groups of cross-posts from non-bots ignore reply counts"""
        mock_low_value.return_value = set()

        params = [
            # Group 1: Post 1 has few replies but is encountered first
            (1, [2, 3], 100, 5),   # 5 replies (first encountered)
            (2, [1, 3], 101, 30),  # 30 replies - SHOULD win
            (3, [1, 2], 102, 80),  # 80 replies - SHOULD win but doesn't

            # Group 2: Post 4 has few replies but is encountered first
            (4, [5, 6], 200, 2),   # 2 replies (first encountered)
            (5, [4, 6], 201, 40),  # 40 replies - SHOULD win
            (6, [4, 5], 202, 120), # 120 replies - SHOULD win but doesn't

            # Independent post with no cross-posts
            (7, None, 300, 10)
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        # BUG: Current behavior returns [1, 4, 7] (first posts win)
        # EXPECTED: Should return [3, 6, 7] (posts with most replies should win)
        self.assertEqual(result, [3, 6, 7], "Posts with most replies should be chosen in each cross-post group")

    @patch('app.utils.low_value_reposters')
    def test_bug_mixed_bots_and_non_bots(self, mock_low_value):
        """Test bot deprioritization and non-bot reply count selection"""
        mock_low_value.return_value = {100}  # User 100 is a bot

        params = [
            # Group 1: Bot post - should choose non-bot with highest reply count
            (1, [2, 3], 100, 5),   # Bot with 5 replies - should be replaced
            (2, [1, 3], 101, 30),  # Non-bot with 30 replies
            (3, [1, 2], 102, 80),  # Non-bot with 80 replies - should win

            # Group 2: Non-bot post - should choose post with highest reply count
            (4, [5, 6], 200, 2),   # Non-bot with 2 replies
            (5, [4, 6], 201, 40),  # Non-bot with 40 replies
            (6, [4, 5], 202, 120), # Non-bot with 120 replies - should win
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        # Should return [3, 6] (highest reply count wins, bots deprioritized)
        self.assertEqual(result, [3, 6], "Bots should be replaced by non-bots, and highest reply count should win")

    @patch('app.utils.low_value_reposters')
    def test_bot_with_only_bot_alternatives(self, mock_low_value):
        """Test that when bot post has only bot alternatives, highest reply count bot wins"""
        mock_low_value.return_value = {100, 101, 102}  # All users are bots

        params = [
            (1, [2, 3], 100, 5),   # Bot with 5 replies
            (2, [1, 3], 101, 30),  # Bot with 30 replies
            (3, [1, 2], 102, 80),  # Bot with 80 replies - should win
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        # Even though all are bots, choose the one with most replies
        self.assertEqual(result, [3], "When all alternatives are bots, choose bot with most replies")

    @patch('app.utils.low_value_reposters')
    def test_bot_deprioritization_basic(self, mock_low_value):
        """Test that bot posts are replaced by non-bot alternatives even if bot has more replies"""
        mock_low_value.return_value = {100}  # User 100 is a bot

        params = [
            (1, [2], 100, 100),  # Bot with 100 replies
            (2, [1], 101, 5),    # Non-bot with 5 replies - should win despite fewer replies
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        # Non-bot should win even though it has fewer replies
        self.assertEqual(result, [2], "Non-bot should be preferred over bot regardless of reply count")

    @patch('app.utils.low_value_reposters')
    def test_bot_deprioritization_chooses_best_non_bot(self, mock_low_value):
        """Test that when replacing bot, the non-bot with most replies is chosen"""
        mock_low_value.return_value = {100}  # User 100 is a bot

        params = [
            (1, [2, 3, 4], 100, 1000),  # Bot with 1000 replies
            (2, [1, 3, 4], 101, 10),     # Non-bot with 10 replies
            (3, [1, 2, 4], 102, 50),     # Non-bot with 50 replies - should win
            (4, [1, 2, 3], 103, 25),     # Non-bot with 25 replies
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        # Post 3 should win (non-bot with most replies)
        self.assertEqual(result, [3], "When replacing bot, choose non-bot with most replies")

    @patch('app.utils.low_value_reposters')
    def test_post_with_no_valid_alternatives_not_hidden(self, mock_low_value):
        """Test that posts with cross-post references that don't exist are not hidden"""
        mock_low_value.return_value = set()

        params = [
            (1, [999, 998], 100, 10),  # Has cross-posts but they don't exist in dataset
            (2, None, 101, 20),         # Regular post
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        # Both posts should remain (post 1 shouldn't be hidden just because its cross-posts don't exist)
        self.assertEqual(result, [1, 2], "Posts with non-existent cross-posts should not be hidden")

    @patch('app.utils.low_value_reposters')
    def test_bot_post_with_no_valid_alternatives_not_hidden(self, mock_low_value):
        """Test that bot posts with no valid alternatives are not hidden"""
        mock_low_value.return_value = {100}  # User 100 is a bot

        params = [
            (1, [999], 100, 10),  # Bot with cross-post that doesn't exist
            (2, None, 101, 20),    # Regular post
        ]
        result = dedupe_post_ids(params, limit_to_visible=False)
        # Both posts should remain (bot post shouldn't be hidden just because its cross-post doesn't exist)
        self.assertEqual(result, [1, 2], "Bot posts with no valid alternatives should not be hidden")

    @patch('app.utils.low_value_reposters')
    def test_bug_order_matters_for_non_bots(self, mock_low_value):
        """BUG: Order of posts affects which one is chosen for non-bots"""
        mock_low_value.return_value = set()

        # Test with one order
        params1 = [
            (1, [2, 3], 100, 200), # 200 replies, encountered first
            (2, [1, 3], 101, 50),  # 50 replies
            (3, [1, 2], 102, 10),  # 10 replies
        ]
        result1 = dedupe_post_ids(params1, limit_to_visible=False)

        # Test with reversed order (but reply counts are the same)
        params2 = [
            (3, [1, 2], 102, 10),  # 10 replies, encountered first
            (2, [1, 3], 101, 50),  # 50 replies
            (1, [2, 3], 100, 200), # 200 replies
        ]
        result2 = dedupe_post_ids(params2, limit_to_visible=False)

        # EXPECTED: Both should return [1] (post with most replies)
        # BUG: result1 returns [1], result2 returns [3] (order matters when it shouldn't)
        self.assertEqual(result1, [1], "Should choose post with most replies (200)")
        self.assertEqual(result2, [1], "Should choose post with most replies (200) regardless of order")


if __name__ == '__main__':
    unittest.main()
