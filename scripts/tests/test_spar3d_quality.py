from scripts.spar3d_furniture_experiment import accepted_for_display


def test_small_visual_gain_cannot_override_bad_measured_geometry():
    record = {
        "box_iou": 1.0,
        "lidar_to_surface_cm": 11.43,
        "texture_painted_fraction": 0.447,
        "photo_ssim_mean": 0.636,
        "views": [{"lidar_ssim": 0.621} for _ in range(5)],
    }
    assert not accepted_for_display(record)


def test_good_geometry_still_needs_five_independent_views():
    record = {
        "box_iou": 0.9,
        "lidar_to_surface_cm": 3.0,
        "texture_painted_fraction": 0.7,
        "photo_ssim_mean": 0.7,
        "views": [{"lidar_ssim": 0.6} for _ in range(4)],
    }
    assert not accepted_for_display(record)
    record["views"].append({"lidar_ssim": 0.6})
    assert accepted_for_display(record)
