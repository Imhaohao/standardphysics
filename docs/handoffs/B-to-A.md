# B to A: I touched your lane, at Boris's request

He asked for delete on the saved scans page while you were away, and said
everyone is subscribed to pushes so changes are fine. Flagging it rather than
letting you find it in a diff.

## What changed in `apps/ios`

- `CaptureLibrary.remove(_:)` in `ScanExporter.swift` — removes one capture
  directory.
- `ScanUploadClient.delete(id:)` — `DELETE /api/scans/{id}`. A 404 counts as
  success: the phone asked for the scan to not be there, and it is not there.
- `AppModel.deleteScan(_:)` in `AppRootView.swift` — clears the phone first,
  then the server, and says nothing about the server either way.
- `SavedScanRow`, a new private view, replacing the inline row markup in
  `SavedScansView`. Swipe left past 72pt or press the trash, then confirm.

Two judgement calls you may want to revisit:

**Swipe is a custom `DragGesture`, not `.swipeActions`.** Saved scans live in a
`VStack` inside a `ScrollView`, and `.swipeActions` only works inside a `List`.
Converting to a `List` there meant nesting scroll views, so the gesture is hand
rolled: reveal track behind, 96pt wide, triggers at 72.

**The trash button stays alongside the swipe.** Swipe alone is invisible until
someone already knows to try it, and the repo's UI rules are explicit about
controls that only explain themselves after you use them.

## What it does not do

Nothing is queued for retry if the server is unreachable. The capture leaves the
phone regardless, so a scan the server still holds becomes invisible to the
owner. If you want that reconciled, it belongs in your upload store rather than
in the row.

`xcodebuild` succeeds on the iPhone 17 Pro simulator.
