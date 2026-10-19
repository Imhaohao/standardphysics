import CoreImage
import Foundation
import ImageIO

/// Turns the camera's landscape YCbCr frame into a small portrait JPEG for lining up a resume.
nonisolated enum SnapshotEncoder {
    static let longestSide: CGFloat = 640
    static let quality: CGFloat = 0.6

    private static let context = CIContext(options: [.cacheIntermediates: false])

    @concurrent
    static func jpeg(from frame: CVPixelBufferWrapper) async -> Data? {
        let portrait = CIImage(cvPixelBuffer: frame.buffer).oriented(.right)
        let scale = min(1, longestSide / max(portrait.extent.width, portrait.extent.height))
        let scaled = portrait.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
        let options = [CIImageRepresentationOption(rawValue: kCGImageDestinationLossyCompressionQuality as String): quality]
        return context.jpegRepresentation(of: scaled, colorSpace: colorSpace, options: options)
    }
}
