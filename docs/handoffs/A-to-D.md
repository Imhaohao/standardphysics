# A to D: local workspace and detailed LiDAR handoff

The Lane A human approved Lane D's no-sign-in local demo. iOS loads `/scans/{scanID}` directly on the configured local workspace origin, with same-origin navigation and main-frame `nativeCapture` / `scanShop` checks. Hosted no-sign-in workspaces remain disabled; no provider key enters the WebView.

The real `ravida` upload is ready: `af42f6cd-d228-4dd8-8790-aff0890fee5b`. It includes a 77,304,881-byte H.264 walkthrough and 284 frame images. The metadata mapping is a binary plist. iOS uploads mapping, poses and coverage first, then USDZ and room JSON, and immediately finalizes; video/images continue afterward. The processing input therefore includes coverage and mapping without waiting for video. Late media should remain post-processing extras until D defines a reprocessing protocol.

The phone also saved `lidar-mesh.json`: 93 parts, 460,497 vertices and 819,498 triangles. It is visible in the native Details view and shareable, but not uploaded because `ArtifactKind` has no raw LiDAR entry. Please add an agreed `lidar_mesh` kind and viewer support; do not treat this file as RoomPlan JSON or silently replace the semantic model.

Current local format: `{ "parts": [{ "id": "UUID", "transform": [16 column-major floats], "vertices": [x,y,z,...], "triangles": [three UInt32 indices per triangle] }] }`. Vertices are anchor-local meters, transforms place them in the same Y-up AR world as RoomPlan. This is observed untextured geometry, not recognized object labels. Ravida's RoomPlan objects are 3 tables, 11 chairs and 1 storage unit; no TV was recognized, while the raw mesh preserves additional observed shapes.
