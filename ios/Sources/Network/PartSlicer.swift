import Foundation

nonisolated enum PartSlicerError: Error, Equatable {
    case partOutOfRange
}

/// Copies one byte range of a file into its own file. Background upload tasks need a file
/// per part; slicing streams in small chunks so memory stays flat for any part size.
nonisolated struct PartSlicer: Sendable {
    static let copyChunkSize = 1 << 20

    static func partCount(fileSize: Int64, partSize: Int) -> Int {
        Int((fileSize + Int64(partSize) - 1) / Int64(partSize))
    }

    static func partLength(partNumber: Int, fileSize: Int64, partSize: Int) -> Int64 {
        let offset = Int64(partNumber - 1) * Int64(partSize)
        return max(0, min(Int64(partSize), fileSize - offset))
    }

    /// Part numbers are 1-based, as S3 multipart requires.
    @concurrent
    func slice(source: URL, partNumber: Int, partSize: Int, to destination: URL) async throws -> Int64 {
        let fileSize = try Self.fileSize(of: source)
        let length = Self.partLength(partNumber: partNumber, fileSize: fileSize, partSize: partSize)
        guard partNumber >= 1, length > 0 else { throw PartSlicerError.partOutOfRange }
        let offset = UInt64(partNumber - 1) * UInt64(partSize)
        try Self.copyRange(from: source, offset: offset, length: length, to: destination)
        return length
    }

    private static func fileSize(of url: URL) throws -> Int64 {
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        return (attributes[.size] as? NSNumber)?.int64Value ?? 0
    }

    private static func copyRange(from source: URL, offset: UInt64, length: Int64, to destination: URL) throws {
        try FileManager.default.createDirectory(
            at: destination.deletingLastPathComponent(), withIntermediateDirectories: true
        )
        FileManager.default.createFile(atPath: destination.path, contents: nil)
        let reader = try FileHandle(forReadingFrom: source)
        let writer = try FileHandle(forWritingTo: destination)
        defer {
            try? reader.close()
            try? writer.close()
        }
        try reader.seek(toOffset: offset)
        var remaining = length
        while remaining > 0 {
            let chunk = try reader.read(upToCount: Int(min(Int64(copyChunkSize), remaining))) ?? Data()
            guard !chunk.isEmpty else { break }
            try writer.write(contentsOf: chunk)
            remaining -= Int64(chunk.count)
        }
    }
}
