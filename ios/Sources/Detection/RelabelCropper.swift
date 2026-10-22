import CoreGraphics
import CoreImage
import Foundation
import ImageIO

/// A photo of one RoomPlan object, for the server to check what it really is.
nonisolated struct RelabelCrop: Sendable, Equatable {
    /// RoomPlan's identifier, as sp-core and the server know the object.
    let objectID: String
    let jpeg: Data
}

/// Picks, for each doubtful RoomPlan object, the keyframe where its box is largest and fully in
/// view, and cuts the box out of it.
nonisolated enum RelabelCropper {
    /// Boxes smaller than this share of the image are too small to tell anything from.
    static let minimumImageShare: CGFloat = 0.01
    /// Extra room around the box on each side, as a share of its size.
    static let padding: CGFloat = 0.1
    static let longestSide: CGFloat = 768
    static let quality: CGFloat = 0.8

    struct Choice: Equatable {
        let frameIndex: Int
        /// In captured-image pixels, origin top-left, padded and clamped to the image.
        let rect: CGRect
    }

    static func bestFrame(for object: CapturedRoomGeometry.PlannedObject, among cameras: [CameraGeometry]) -> Choice? {
        let visible = cameras.enumerated().compactMap { index, camera -> (Choice, CGFloat)? in
            guard let rect = BoxProjection.visibleRect(transform: object.transform, dimensions: object.dimensions, camera: camera)
            else { return nil }
            let share = imageShare(of: rect, imageSize: camera.imageSize)
            guard share >= minimumImageShare else { return nil }
            return (Choice(frameIndex: index, rect: padded(rect, imageSize: camera.imageSize)), share)
        }
        return visible.max { $0.1 < $1.1 }?.0
    }

    static func imageShare(of rect: CGRect, imageSize: SIMD2<Float>) -> CGFloat {
        let image = CGRect(x: 0, y: 0, width: CGFloat(imageSize.x), height: CGFloat(imageSize.y))
        let inside = rect.intersection(image)
        guard !inside.isNull, image.width > 0, image.height > 0 else { return 0 }
        return inside.width * inside.height / (image.width * image.height)
    }

    static func padded(_ rect: CGRect, imageSize: SIMD2<Float>) -> CGRect {
        let image = CGRect(x: 0, y: 0, width: CGFloat(imageSize.x), height: CGFloat(imageSize.y))
        return rect.insetBy(dx: -rect.width * padding, dy: -rect.height * padding).intersection(image)
    }

    /// Crops of the room's doubtful objects, off the main actor. Objects never fully seen are skipped.
    @concurrent
    static func crops(for room: CapturedRoomGeometry, keyframes: [Keyframe]) async -> [RelabelCrop] {
        let cameras = keyframes.map(\.camera)
        return RelabelSelection.candidates(in: room).compactMap { object in
            guard let choice = bestFrame(for: object, among: cameras),
                  let jpeg = cut(choice.rect, from: keyframes[choice.frameIndex])
            else { return nil }
            return RelabelCrop(objectID: object.identifier, jpeg: jpeg)
        }
    }

    /// `rect` is in captured-image pixels with the origin top-left; Core Image's origin is bottom-left.
    static func cut(_ rect: CGRect, from keyframe: Keyframe) -> Data? {
        guard let image = CIImage(data: keyframe.jpeg) else { return nil }
        let scaled = rect.applying(CGAffineTransform(scaleX: keyframe.scale, y: keyframe.scale))
        let flipped = CGRect(x: scaled.minX, y: image.extent.height - scaled.maxY, width: scaled.width, height: scaled.height)
        let cropped = image.cropped(to: flipped.intersection(image.extent))
        guard !cropped.extent.isEmpty else { return nil }
        let upright = cropped.oriented(.right)
        let shrink = min(1, longestSide / max(upright.extent.width, upright.extent.height))
        let resized = upright.transformed(by: CGAffineTransform(scaleX: shrink, y: shrink))
        return KeyframeEncoder.jpeg(resized, quality: quality)
    }
}
