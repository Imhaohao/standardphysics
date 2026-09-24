"""Photo-mesh 500 benchmark plumbing and unlit raster checks.

The raster fixture re-projects a textured wall with the frozen pixel-convention
camera and compares against the analytical projection, so a transposed camera
basis or a wrong perspective-correct interpolation cannot silently pass.
"""
import numpy as np
import pytest

pytest.importorskip("numba", reason="offline raster requires reconstruction extra")
pytest.importorskip("trimesh", reason="offline raster requires reconstruction extra")

from standardphysics_pipeline.render_efficiency.photo_mesh_500 import (
    RasterCamera,
    camera_from_room,
)

try:
    from render_photo_mesh_raster import raster_frame
except ModuleNotFoundError as error:  # pragma: no cover
    pytest.skip(f"raster lives in scripts/ (PYTHONPATH=scripts): {error}", allow_module_level=True)


def test_scene_conversion_matches_bake_mapping():
    room_to_camera = np.zeros((4, 4))
    room_to_camera[:3, :3] = np.array([[0.0, 0.0, -1.0], [1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])
    converted = camera_from_room("x", room_to_camera, 800.0, 800.0, 320.0, 320.0, 640, 640)
    # a room point must land where the original room-frame projection puts it
    camera_coords = converted.scene_to_camera[:3, :3] @ np.array([0.0, 0.0, -1.0]) + converted.scene_to_camera[:3, 3]
    np.testing.assert_allclose(camera_coords, [0.0, 0.0, -1.0], atol=1e-9)


def test_captured_crop_shifts_principal_point_only():
    from standardphysics_pipeline.render_efficiency.photo_mesh_500 import build_captured_view
    from standardphysics_pipeline.textures.camera import PhotoCamera

    camera = PhotoCamera("frame-0000", np.eye(4), 1333.9, 1333.9, 960.7, 725.1, 1920, 1440, 0)
    cropped = build_captured_view("frame-0000", camera)
    assert cropped.cx == pytest.approx(960.7 - 240.0)
    assert cropped.cy == pytest.approx(725.1)
    # crop does not change the focal length (pixels stay native scale)
    assert cropped.fx == 1333.9 and cropped.fy == 1333.9
    assert cropped.width == 1440 and cropped.height == 1440


def texture_wall():
    ys, xs = np.mgrid[0:128, 0:128]
    texture = np.stack([
        (128 + 120 * np.sin(xs / 9.0) * np.cos(ys / 8.0)),
        (128 + 110 * np.sin(ys / 11.0 + 1.7) * np.cos(xs / 10.0)),
        (128 + 100 * np.sin((xs + ys) / 13.0)),
    ], axis=-1).clip(0, 255).astype(np.uint8)
    return texture


def raster_wall(texture, camera, view_size):
    vertices = np.array([[-1.0, -1.0, 2.0], [1.0, -1.0, 2.0], [1.0, 1.0, 2.0], [-1.0, 1.0, 2.0]], dtype=np.float32)
    faces = np.array([[0, 2, 1], [0, 3, 2]], dtype=np.int32)
    uvs = np.array([[0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]], dtype=np.float32)
    colour, depth, _, _, _ = raster_frame(
        vertices, faces, uvs, np.array([0, 0], dtype=np.int32), [texture],
        np.zeros((8, 3), dtype=np.float32), camera.scene_to_camera[:3, :3].astype(np.float32),
        camera.scene_to_camera[:3, 3].astype(np.float32), camera.fx, camera.fy, camera.cx, camera.cy,
        view_size, view_size, 0)
    return colour, depth


def analytical(texture, camera, view_size):
    ys, xs = np.mgrid[0:view_size, 0:view_size]
    rays = np.stack([(xs - camera.cx) / camera.fx, (ys - camera.cy) / camera.fy, np.ones((view_size, view_size))], axis=-1)
    rot = camera.scene_to_camera[:3, :3]
    trans = camera.scene_to_camera[:3, 3]
    p0 = -rot.T @ trans
    directions = rays @ rot
    depth = (2.0 - p0[2]) / directions[..., 2]
    world = depth[..., None] * directions + p0[None, None, :]
    tex = np.asarray(texture, dtype=np.float64)
    th, tw = tex.shape[:2]
    u = ((world[..., 0] + 1.0) / 2.0 * tw - 0.5).clip(0, tw - 1.001)
    v = ((1.0 - world[..., 1]) / 2.0 * th - 0.5).clip(0, th - 1.001)
    xi = np.floor(u).astype(np.int64)
    yi = np.floor(v).astype(np.int64)
    fu = u - xi
    fv = v - yi
    x1 = np.minimum(xi + 1, tw - 1)
    y1 = np.minimum(yi + 1, th - 1)
    w00 = (1 - fu) * (1 - fv)
    w10 = fu * (1 - fv)
    w01 = (1 - fu) * fv
    w11 = fu * fv
    sampled = (w00[..., None] * tex[yi, xi] + w10[..., None] * tex[yi, x1] +
               w01[..., None] * tex[y1, xi] + w11[..., None] * tex[y1, x1])
    valid = (depth > 0) & (np.abs(world[..., 0]) < 0.97) & (np.abs(world[..., 1]) < 0.97)
    return sampled, valid


def test_raster_matches_analytic_projection_on_and_off_axis():
    texture = texture_wall()
    view_size = 256
    for position, cx, cy in ((np.array([0.0, 0.0, 0.0]), 128, 128),
                             (np.array([0.05, 0.02, 0.0]), 150, 110)):
        forward = np.array([0.0, 0.0, 2.0]) - position
        up = np.array([0.0, 1.0, 0.0])
        f = forward / np.linalg.norm(forward)
        r = np.cross(f, up)
        r = r / np.linalg.norm(r)
        d = np.cross(f, r)
        d = d / np.linalg.norm(d)
        rot = np.vstack([r, d, f])
        t = -rot @ position
        fx = 160.0
        camera = RasterCamera("t", view_size, view_size, np.column_stack([rot, t]), fx, fx, cx, cy)
        rendered, depth = raster_wall(texture, camera, view_size)
        expected, valid = analytical(texture, camera, view_size)
        rms = np.sqrt(((rendered - expected)[valid] ** 2).mean())
        assert rms < 3.0, f"raster drifted on camera {position}: rms {rms}"
