import unittest
import os
from PIL import Image
from app.utils import make_gallery_thumbnail


class TestGalleryThumbnail(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """load sample images once for all tests."""
        os.chdir("..")                          # Change to project root directory to ensure image and font paths work
        cls.sample_dir = "testing_data/sample_pics"
        cls.image_paths = [
            os.path.join(cls.sample_dir, "DSC07922.JPG"),
            os.path.join(cls.sample_dir, "DSC07923.JPG"),
            os.path.join(cls.sample_dir, "DSC07924.JPG"),
            os.path.join(cls.sample_dir, "DSC07925.JPG"),
            os.path.join(cls.sample_dir, "IMG999.jpg"),
        ]
        cls.images = [Image.open(path) for path in cls.image_paths]

    def setUp(self):
        self.output_dir = "."
        os.makedirs(self.output_dir, exist_ok=True)

    def _save_and_cleanup(self, result, filename):
        if result is not None:
            output_path = os.path.join(self.output_dir, filename)
            result.save(output_path)
            self.addCleanup(lambda fp=output_path: self._cleanup_file(fp))

    def _cleanup_file(self, path):
        # comment these lines out to visually inspect the results
        #if os.path.exists(path):
        #    os.remove(path)
        pass

    def test_empty_list_returns_none(self):
        result = make_gallery_thumbnail([])
        self.assertIsNone(result)

    def test_single_image(self):
        images = [self.images[0]]
        result = make_gallery_thumbnail(images, size=600)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (600, 600))
        self.assertEqual(result.mode, "RGB")
        self._save_and_cleanup(result, "test_single_image.png")

    def test_two_images_side_by_side(self):
        images = [self.images[0], self.images[1]]
        result = make_gallery_thumbnail(images, size=600)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (600, 600))
        self.assertEqual(result.mode, "RGBA")
        self._save_and_cleanup(result, "test_two_images.png")

    def test_three_images_grid(self):
        images = [self.images[0], self.images[1], self.images[2]]
        result = make_gallery_thumbnail(images, size=600)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (600, 600))
        self.assertEqual(result.mode, "RGBA")
        self._save_and_cleanup(result, "test_three_images.png")

    def test_four_images_grid(self):
        images = [self.images[0], self.images[1], self.images[2], self.images[3]]
        result = make_gallery_thumbnail(images, size=600)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (600, 600))
        self.assertEqual(result.mode, "RGBA")
        self._save_and_cleanup(result, "test_four_images.png")

    def test_five_images_with_count_overlay(self):
        images = self.images[:5]
        result = make_gallery_thumbnail(images, size=600)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (600, 600))
        self.assertEqual(result.mode, "RGBA")
        self._save_and_cleanup(result, "test_five_images.png")

    def test_six_images_with_count_overlay(self):
        images = self.images[:3] * 2
        result = make_gallery_thumbnail(images, size=600)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (600, 600))
        self.assertEqual(result.mode, "RGBA")
        self._save_and_cleanup(result, "test_six_images.png")

    def test_custom_size(self):
        images = [self.images[0], self.images[1]]
        result = make_gallery_thumbnail(images, size=400)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (400, 400))
        self.assertEqual(result.mode, "RGBA")
        self._save_and_cleanup(result, "test_custom_size.png")

    def test_single_image_different_aspect_ratios(self):
        landscape = Image.new("RGB", (800, 400), color="red")
        result = make_gallery_thumbnail([landscape], size=200)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (200, 200))
        self._save_and_cleanup(result, "test_landscape_single.png")

    def test_rgba_images(self):
        rgba1 = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        rgba2 = Image.new("RGBA", (100, 100), color=(0, 255, 0, 128))
        result = make_gallery_thumbnail([rgba1, rgba2], size=200)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (200, 200))
        self.assertEqual(result.mode, "RGBA")
        self._save_and_cleanup(result, "test_rgba_images.png")

    def test_mixed_image_modes(self):
        rgb_image = Image.new("RGB", (100, 100), color="blue")
        rgba_image = Image.new("RGBA", (100, 100), color=(255, 0, 0, 200))
        result = make_gallery_thumbnail([rgb_image, rgba_image], size=200)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (200, 200))
        self.assertEqual(result.mode, "RGBA")
        self._save_and_cleanup(result, "test_mixed_modes.png")

    def test_count_overlay_padding(self):
        images = [Image.new("RGB", (100, 100), color="green")] * 5
        result = make_gallery_thumbnail(images, size=600)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (600, 600))
        self._save_and_cleanup(result, "test_count_overlay.png")

    def test_large_count_overlay(self):
        images = self.images[:3] * 4
        result = make_gallery_thumbnail(images, size=600)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (600, 600))
        self._save_and_cleanup(result, "test_large_count.png")

    def test_small_size(self):
        images = [self.images[0], self.images[1]]
        result = make_gallery_thumbnail(images, size=100)
        self.assertIsNotNone(result)
        self.assertEqual(result.size, (100, 100))
        self.assertEqual(result.mode, "RGBA")
        self._save_and_cleanup(result, "test_small_size.png")


if __name__ == '__main__':
    unittest.main()
