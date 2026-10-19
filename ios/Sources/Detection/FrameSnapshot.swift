import ARKit
import CoreVideo

/// What the detector needs from one ARFrame, copied out so the frame can be released at once.
nonisolated struct FrameSnapshot: Sendable {
    let image: CVPixelBufferWrapper
    let depth: DepthSamples?
    let camera: CameraGeometry

    init(image: CVPixelBufferWrapper, depth: DepthSamples?, camera: CameraGeometry) {
        self.image = image
        self.depth = depth
        self.camera = camera
    }

    init(frame: ARFrame) {
        let resolution = frame.camera.imageResolution
        image = CVPixelBufferWrapper(buffer: frame.capturedImage)
        depth = (frame.smoothedSceneDepth ?? frame.sceneDepth).map(DepthSamples.init(depthData:))
        camera = CameraGeometry(
            intrinsics: frame.camera.intrinsics,
            imageSize: SIMD2(Float(resolution.width), Float(resolution.height)),
            cameraToWorld: frame.camera.transform
        )
    }
}

extension DepthSamples {
    nonisolated init(depthData: ARDepthData) {
        let map = depthData.depthMap
        width = CVPixelBufferGetWidth(map)
        height = CVPixelBufferGetHeight(map)
        depths = Self.copyRows(of: map, as: Float.self)
        confidences = depthData.confidenceMap.map { Self.copyRows(of: $0, as: UInt8.self) }
    }

    private nonisolated static func copyRows<Element>(of buffer: CVPixelBuffer, as _: Element.Type) -> [Element] {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        let width = CVPixelBufferGetWidth(buffer)
        let height = CVPixelBufferGetHeight(buffer)
        let bytesPerRow = CVPixelBufferGetBytesPerRow(buffer)
        guard let base = CVPixelBufferGetBaseAddress(buffer) else { return [] }
        return (0..<height).flatMap { row in
            let rowStart = base.advanced(by: row * bytesPerRow).assumingMemoryBound(to: Element.self)
            return Array(UnsafeBufferPointer(start: rowStart, count: width))
        }
    }
}
