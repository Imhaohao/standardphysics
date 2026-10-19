import RealityKit
import simd

/// Shared meshes and materials so entities never allocate their own.
final class OverlayAssets {
    let unitBox = MeshResource.generateBox(size: 1)
    let unitPlane = MeshResource.generatePlane(width: 1, height: 1)

    static func material(_ tint: OverlayStyle.Tint) -> UnlitMaterial {
        var material = UnlitMaterial(color: tint.color)
        if tint.opacity < 1 {
            material.blending = .transparent(opacity: .init(floatLiteral: tint.opacity))
        }
        material.faceCulling = .none
        return material
    }
}

/// Keeps one entity tree per `SceneShape`, updating in place by id instead of rebuilding.
final class LiveSceneRenderer {
    /// Dimension changes smaller than this only move the entity, without re-laying out its strokes.
    static let relayoutTolerance: Float = 0.01

    private struct RenderedShape {
        let container: Entity
        let fill: ModelEntity?
        let strokes: [ModelEntity]
        var shape: SceneShape
    }

    let root = Entity()
    private let assets = OverlayAssets()
    private var rendered: [String: RenderedShape] = [:]
    private var fillMaterials: [SceneShapeStyle: UnlitMaterial] = [:]
    private var strokeMaterials: [SceneShapeStyle: UnlitMaterial] = [:]

    func apply(_ shapes: [SceneShape]) {
        let incoming = Set(shapes.map(\.id))
        for id in rendered.keys where !incoming.contains(id) {
            rendered.removeValue(forKey: id)?.container.removeFromParent()
        }
        shapes.forEach(update)
    }

    private func update(_ shape: SceneShape) {
        guard var existing = rendered[shape.id], existing.shape.style == shape.style else {
            rendered[shape.id]?.container.removeFromParent()
            rendered[shape.id] = makeRendered(shape)
            return
        }
        existing.container.transform = Transform(matrix: shape.transform)
        if needsRelayout(from: existing.shape.dimensions, to: shape.dimensions) {
            layout(existing.fill, existing.strokes, for: shape)
        }
        existing.shape = shape
        rendered[shape.id] = existing
    }

    private func needsRelayout(from old: SIMD3<Float>, to new: SIMD3<Float>) -> Bool {
        simd_reduce_max(simd_abs(old - new)) > Self.relayoutTolerance
    }

    private func makeRendered(_ shape: SceneShape) -> RenderedShape {
        let container = Entity()
        container.transform = Transform(matrix: shape.transform)
        let fill = fillMaterial(for: shape.style).map { ModelEntity(mesh: assets.unitPlane, materials: [$0]) }
        let strokeMaterial = strokeMaterial(for: shape.style)
        let strokeCount = strokes(for: shape).count
        let strokes = (0..<strokeCount).map { _ in ModelEntity(mesh: assets.unitBox, materials: [strokeMaterial]) }
        if let fill { container.addChild(fill) }
        strokes.forEach { container.addChild($0) }
        layout(fill, strokes, for: shape)
        root.addChild(container)
        return RenderedShape(container: container, fill: fill, strokes: strokes, shape: shape)
    }

    private func layout(_ fill: ModelEntity?, _ strokeEntities: [ModelEntity], for shape: SceneShape) {
        fill?.scale = SIMD3(shape.dimensions.x, shape.dimensions.y, 1)
        for (entity, stroke) in zip(strokeEntities, strokes(for: shape)) {
            var scale = SIMD3<Float>(repeating: OverlayStyle.Scene.edgeThickness)
            scale[stroke.axis] = max(stroke.length, OverlayStyle.Scene.edgeThickness)
            entity.position = stroke.center
            entity.scale = scale
        }
    }

    private func strokes(for shape: SceneShape) -> [EdgeStroke] {
        EdgeLayout.strokes(dimensions: shape.dimensions, isPlanar: shape.style.isPlanar, isDashed: shape.style == .detectedObject)
    }

    private func fillMaterial(for style: SceneShapeStyle) -> UnlitMaterial? {
        if let cached = fillMaterials[style] { return cached }
        guard let tint = fillTint(for: style) else { return nil }
        let material = OverlayAssets.material(tint)
        fillMaterials[style] = material
        return material
    }

    private func strokeMaterial(for style: SceneShapeStyle) -> UnlitMaterial {
        if let cached = strokeMaterials[style] { return cached }
        let material = OverlayAssets.material(edgeTint(for: style))
        strokeMaterials[style] = material
        return material
    }

    private func fillTint(for style: SceneShapeStyle) -> OverlayStyle.Tint? {
        switch style {
        case .wall: OverlayStyle.Scene.wallFill
        case .opening: OverlayStyle.Scene.openingFill
        case .window: OverlayStyle.Scene.windowFill
        case .object, .detectedObject: nil
        }
    }

    private func edgeTint(for style: SceneShapeStyle) -> OverlayStyle.Tint {
        switch style {
        case .wall: OverlayStyle.Scene.wallEdge
        case .opening: OverlayStyle.Scene.openingEdge
        case .window: OverlayStyle.Scene.windowEdge
        case .object: OverlayStyle.Scene.objectEdge
        case .detectedObject: OverlayStyle.Scene.detectedEdge
        }
    }
}
