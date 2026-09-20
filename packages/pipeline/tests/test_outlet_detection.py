"""Tests for photographic outlet detection, crop/tile transforms, and coordinate invariants."""

from __future__ import annotations

import io
import math
import pathlib
import pytest
from PIL import Image, ImageDraw

from standardphysics_pipeline.discovery.detect import (
    BOX_SCALE,
    Detection,
    DetectionError,
    EncodedFrame,
    QUARTER_TURNS_CLOCKWISE,
    _clamped,
    _one_detection,
    _pixel_box,
    box_iou,
    detect_objects,
    extract_padded_crop,
    generate_tiles,
    map_crop_box_to_sensor,
    map_crop_point_to_sensor,
)


def create_asymmetric_test_image(width=1920, height=1440) -> Image.Image:
    """Creates an asymmetric test image with an 'F' shaped marker at a known off-center location.
    
    The 'F' has vertical line from (200, 300) to (200, 500), horizontal top bar from (200, 300) to (350, 300),
    and mid bar from (200, 380) to (300, 380).
    Because 'F' is neither horizontally nor vertically symmetric, rotations and x/y swaps cannot pass unnoticed.
    """
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    # Background pattern to ensure uniqueness across quadrants
    draw.rectangle([0, 0, width // 2, height // 2], fill=(220, 230, 240))
    # Draw 'F' marker in upper-left quadrant
    draw.line([(200, 300), (200, 500)], fill=(255, 0, 0), width=10)
    draw.line([(200, 300), (350, 300)], fill=(255, 0, 0), width=10)
    draw.line([(200, 380), (300, 380)], fill=(255, 0, 0), width=10)
    return img


class TestRotationAndCoordinateTransforms:
    """Tests for all quarter turns ensuring sensor coordinates are recovered exactly."""

    @pytest.mark.parametrize("orientation,expected_turns", [
        ("landscape_right", 0),
        ("portrait", 1),
        ("landscape_left", 2),
        ("portrait_upside_down", 3),
    ])
    def test_all_rotations_map_box_back_to_same_sensor_pixels(self, orientation, expected_turns):
        w, h = 1920, 1440
        # Target sensor box: [left, top, right, bottom]
        sensor_box = (200.0, 300.0, 350.0, 500.0)
        left, top, right, bottom = sensor_box

        # Compute what normalized [ymin, xmin, ymax, xmax] the model would see in the upright image
        # In upright image after `expected_turns` clockwise:
        # A point (x, y) turns:
        # 1 turn (portrait): (x, y) -> (h - 1 - y, x) [normalized: (1-y_norm, x_norm) or depending on turn convention]
        # Our detect.py un-turns: for _ in range(turns): left, top, right, bottom = top, 1.0 - right, bottom, 1.0 - left
        # Let's verify by inverting:
        # If un-turn is: left_out, top_out, right_out, bottom_out = top, 1 - right, bottom, 1 - left
        # Then forward turn of (left_s, top_s, right_s, bottom_s) normalized is:
        # 1 forward turn: (left, top, right, bottom) -> (1 - bottom, left, 1 - top, right)
        
        # Test directly with map_crop_box_to_sensor
        # When turns=0:
        upright_top = top / h
        upright_left = left / w
        upright_bottom = bottom / h
        upright_right = right / w
        
        # Apply forward turns to simulate model output on upright image:
        for _ in range(expected_turns):
            upright_left, upright_top, upright_right, upright_bottom = (
                1.0 - upright_bottom,
                upright_left,
                1.0 - upright_top,
                upright_right,
            )

        model_box_2d = [
            upright_top * BOX_SCALE,
            upright_left * BOX_SCALE,
            upright_bottom * BOX_SCALE,
            upright_right * BOX_SCALE,
        ]

        mapped = map_crop_box_to_sensor(model_box_2d, (0.0, 0.0, float(w), float(h)), expected_turns)
        assert mapped is not None
        assert mapped[0] == pytest.approx(sensor_box[0], abs=1.0)
        assert mapped[1] == pytest.approx(sensor_box[1], abs=1.0)
        assert mapped[2] == pytest.approx(sensor_box[2], abs=1.0)
        assert mapped[3] == pytest.approx(sensor_box[3], abs=1.0)

    def test_map_crop_point_to_sensor_recovers_point(self):
        crop_box = (100.0, 200.0, 600.0, 800.0) # width 500, height 600
        # Point inside crop at local normalized (0.2, 0.3) -> x = 100 + 0.2*500 = 200, y = 200 + 0.3*600 = 380
        # When turns = 0:
        pt = map_crop_point_to_sensor([300.0, 200.0], crop_box, turns=0)
        assert pt == pytest.approx((200.0, 380.0), abs=0.1)

        # When turns = 1 (portrait):
        # forward turn of (x, y) = (0.2, 0.3) is (1 - 0.3, 0.2) = (0.7, 0.2)
        # model reports y=200, x=700 in upright crop
        pt_turned = map_crop_point_to_sensor([200.0, 700.0], crop_box, turns=1)
        assert pt_turned == pytest.approx((200.0, 380.0), abs=0.1)


class TestCroppingAndTiling:
    """Tests for padding, border clipping, and tile generation."""

    def test_extract_padded_crop_with_padding_clipped_at_borders(self):
        img = Image.new("RGB", (1000, 1000), color=(0, 0, 0))
        # Box near top-left edge: [10, 10, 110, 110]
        box = (10.0, 10.0, 110.0, 110.0)
        # 20% padding is 20px on each side
        # Left and top should clip to 0.0
        cropped, crop_rect = extract_padded_crop(img, box, padding_fraction=0.20)
        assert crop_rect[0] == 0.0 # clipped at 0
        assert crop_rect[1] == 0.0 # clipped at 0
        assert crop_rect[2] == 130.0
        assert crop_rect[3] == 130.0
        assert cropped.size == (130, 130)

    def test_extract_padded_crop_centered(self):
        img = Image.new("RGB", (1000, 1000), color=(0, 0, 0))
        box = (200.0, 300.0, 300.0, 400.0) # 100x100
        cropped, crop_rect = extract_padded_crop(img, box, padding_fraction=0.20)
        assert crop_rect == (180.0, 280.0, 320.0, 420.0)
        assert cropped.size == (140, 140)

    def test_generate_tiles_covers_image_with_overlap(self):
        w, h = 1920, 1440
        tiles = generate_tiles(w, h, tile_size=(1024, 1024), overlap=0.20)
        assert len(tiles) >= 4
        # Verify all tiles are within image bounds
        for left, top, right, bottom in tiles:
            assert 0.0 <= left < right <= w
            assert 0.0 <= top < bottom <= h
            assert right - left <= 1024
            assert bottom - top <= 1024

        # Check coverage: every pixel in the 1920x1440 image must be covered by at least one tile
        step = 100
        for x in range(0, w, step):
            for y in range(0, h, step):
                covered = any(l <= x <= r and t <= y <= b for l, t, r, b in tiles)
                assert covered, f"Pixel ({x}, {y}) is not covered by any tile"

    def test_box_iou_computation(self):
        b1 = (0.0, 0.0, 10.0, 10.0) # area 100
        b2 = (5.0, 0.0, 15.0, 10.0) # intersection 5x10 = 50, union 150 -> IoU = 1/3
        assert box_iou(b1, b2) == pytest.approx(1.0 / 3.0, abs=0.01)

        b3 = (20.0, 20.0, 30.0, 30.0) # disjoint
        assert box_iou(b1, b3) == 0.0


class TestMalformedAndInvalidInputs:
    """Ensures nonfinite, out-of-range, and malformed model outputs are rejected safely."""

    def test_malformed_box_returns_none(self):
        frame = EncodedFrame(b"", 1920, 1440, turns=0)
        assert _pixel_box(None, frame) is None
        assert _pixel_box([], frame) is None
        assert _pixel_box([10, 20], frame) is None
        assert _pixel_box([10, 20, 30], frame) is None
        assert _pixel_box(["a", "b", "c", "d"], frame) is None
        assert _pixel_box([float("nan"), 100, 200, 300], frame) is None
        assert _pixel_box([100, float("inf"), 200, 300], frame) is None

    def test_zero_area_or_sliver_box_is_rejected(self):
        frame = EncodedFrame(b"", 1920, 1440, turns=0)
        # Box with 0 width: [100, 200, 300, 200]
        assert _pixel_box([100, 200, 300, 200], frame) is None
        # Tiny sliver below MIN_BOX_FRACTION
        assert _pixel_box([100, 100, 101, 101], frame) is None

    def test_category_and_confuser_classification(self):
        frame = EncodedFrame(b"", 1920, 1440, turns=0)
        outlet_det = _one_detection({"name": "electrical outlet", "box_2d": [100, 100, 200, 200], "confidence": 0.95}, frame, "f-01")
        assert outlet_det is not None
        assert outlet_det.is_outlet is True
        assert outlet_det.is_confuser is False
        assert outlet_det.review_status == "detected"

        switch_det = _one_detection({"name": "light switch", "box_2d": [100, 100, 200, 200], "confidence": 0.90}, frame, "f-01")
        assert switch_det is not None
        assert switch_det.is_outlet is False
        assert switch_det.is_confuser is True
        assert switch_det.review_status == "rejected_confuser"


class TestTransportAndProviderFailures:
    """Verifies that provider errors raise DetectionError and valid empty answers return empty list."""

    def test_provider_error_raises_detection_error(self, tmp_path):
        img_p = tmp_path / "test.jpg"
        Image.new("RGB", (100, 100)).save(img_p)

        def failing_transport(url, body, headers):
            raise OSError("Connection refused")

        with pytest.raises(DetectionError, match="vision model did not answer"):
            detect_objects(img_p, "frame-01", transport=failing_transport)

    def test_valid_empty_response_returns_empty_list(self, tmp_path):
        img_p = tmp_path / "test.jpg"
        Image.new("RGB", (100, 100)).save(img_p)

        def empty_transport(url, body, headers):
            return {
                "choices": [{
                    "message": {
                        "content": '{"objects": []}'
                    }
                }]
            }

        results = detect_objects(img_p, "frame-01", transport=empty_transport)
        assert results == []
