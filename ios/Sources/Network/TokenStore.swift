import Foundation
import Security

nonisolated protocol TokenStoring: Sendable {
    func token() -> String?
    func save(_ token: String) throws
    func clear()
}

nonisolated struct KeychainError: Error, Equatable, Sendable {
    let status: OSStatus
}

/// AfterFirstUnlock keeps the token readable while the phone is locked, which background
/// upload completion needs when it has to re-request expired part URLs.
nonisolated final class KeychainTokenStore: TokenStoring {
    private let service: String
    private let account: String

    init(service: String = "com.tarunyadgirkar.standardphysics.api", account: String = "access-token") {
        self.service = service
        self.account = account
    }

    func token() -> String? {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func save(_ token: String) throws {
        let data = Data(token.utf8)
        let update = [kSecValueData as String: data]
        let status = SecItemUpdate(baseQuery() as CFDictionary, update as CFDictionary)
        if status == errSecSuccess { return }
        guard status == errSecItemNotFound else { throw KeychainError(status: status) }
        var insert = baseQuery()
        insert[kSecValueData as String] = data
        insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(insert as CFDictionary, nil)
        guard addStatus == errSecSuccess else { throw KeychainError(status: addStatus) }
    }

    func clear() {
        SecItemDelete(baseQuery() as CFDictionary)
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}
