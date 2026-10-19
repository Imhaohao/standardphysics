import Foundation

typealias Sleeper = @Sendable (Duration) async throws -> Void

nonisolated enum DefaultSleeper {
    static let sleep: Sleeper = { try await Task.sleep(for: $0) }
}

/// Exponential backoff with "equal jitter": half the ceiling is fixed, half is random.
nonisolated struct Backoff: Sendable {
    var base: Duration = .milliseconds(500)
    var maximum: Duration = .seconds(30)
    var jitter: @Sendable () -> Double = { Double.random(in: 0...1) }

    func delay(forAttempt attempt: Int) -> Duration {
        let exponent = min(max(attempt, 0), 20)
        let ceiling = min(base * pow(2.0, Double(exponent)), maximum)
        let fixedHalf = ceiling / 2
        return fixedHalf + fixedHalf * min(max(jitter(), 0), 1)
    }
}

nonisolated struct RetryPolicy: Sendable {
    var maxAttempts = 4
    var backoff = Backoff(base: .milliseconds(400), maximum: .seconds(20))

    static let none = RetryPolicy(maxAttempts: 1)

    /// Nil means give up. Only idempotent calls are ever retried, so a flaky connection
    /// cannot double-submit a sign-in or similar one-shot request.
    func delay(afterFailure error: APIError, attemptsMade: Int, idempotent: Bool) -> Duration? {
        guard idempotent, error.isTransient, attemptsMade < maxAttempts else { return nil }
        let computed = backoff.delay(forAttempt: attemptsMade - 1)
        guard let serverHint = error.suggestedRetryDelay else { return computed }
        return max(computed, .seconds(serverHint))
    }
}
