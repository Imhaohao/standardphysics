import CoreGraphics
import Observation
import simd

/// A label after projection and layout, ready to draw in view points.
struct PlacedOverlayLabel: Equatable, Identifiable {
    let label: OverlayLabel
    let anchor: CGPoint
    let frame: CGRect
    let span: [CGPoint]

    var id: String { label.id }
}

/// What the live overlay draws. Feed it with `update(elements:detections:findings:)` whenever capture publishes.
@Observable
final class LiveSceneModel {
    private(set) var elements: [LiveElement] = []
    private(set) var detections: [Detection] = []
    private(set) var findings: [Finding] = []
    private(set) var measurements = LiveMeasurements.empty
    private(set) var shapes: [SceneShape] = []
    private(set) var labels: [OverlayLabel] = []
    /// Written by the scene view each frame after projecting `labels`.
    var placedLabels: [PlacedOverlayLabel] = []
    var showsMeshTint = true
    /// Dynamic Type multiplier for label sizes, set by the view.
    var labelScale: CGFloat = 1

    init() {}

    func update(elements: [LiveElement], detections: [Detection], findings: [Finding]) {
        let elementsChanged = elements != self.elements
        let detectionsChanged = detections != self.detections
        let findingsChanged = findings != self.findings
        guard elementsChanged || detectionsChanged || findingsChanged else { return }
        self.elements = elements
        self.detections = detections
        self.findings = findings
        if elementsChanged {
            measurements = MeasurementEstimator.estimate(from: elements)
        }
        if elementsChanged || detectionsChanged {
            shapes = SceneShapeBuilder.shapes(elements: elements, detections: detections)
        }
        labels = OverlayLabelBuilder.labels(measurements: measurements.measurements, findings: findings, elements: elements)
    }

    func update(from capture: some CaptureControlling) {
        update(elements: capture.liveElements, detections: capture.detections, findings: capture.provisionalFindings)
    }
}
