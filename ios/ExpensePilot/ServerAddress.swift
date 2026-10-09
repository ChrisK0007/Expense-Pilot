import Foundation

enum AppError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let text) = self { return text }; return nil }
}

enum ServerAddress {
    static func parse(_ text: String, allowLocalHTTP: Bool) throws -> URL {
        guard var parts = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = parts.scheme?.lowercased(), let host = parts.host?.lowercased(), !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              parts.path.isEmpty || parts.path == "/" else {
            throw AppError.message("Enter the server’s base address, such as https://expenses.example.com, without a login path, query or password.")
        }
        guard parts.port == nil || (1...65535).contains(parts.port!) else { throw AppError.message("Enter a valid server port.") }
        if scheme != "https" {
            guard scheme == "http", allowLocalHTTP, isLocal(host) else {
                throw AppError.message("Use HTTPS, or explicitly allow HTTP for a private IP address or .local hostname.")
            }
        }
        parts.scheme = scheme; parts.host = host; parts.path = "/"
        guard let url = parts.url else { throw AppError.message("Invalid server address.") }
        return url
    }
    static func isLocal(_ host: String) -> Bool {
        if host.hasSuffix(".local") { return true }
        let components = host.split(separator: ".", omittingEmptySubsequences: false)
        guard components.count == 4, components.allSatisfy({ !$0.isEmpty && $0.allSatisfy(\.isNumber) }) else { return false }
        let octets = components.compactMap { Int($0) }
        guard octets.count == 4, octets.allSatisfy({ (0...255).contains($0) }) else { return false }
        return octets[0] == 10 || (octets[0] == 192 && octets[1] == 168) || (octets[0] == 172 && (16...31).contains(octets[1]))
    }
    static func sameOrigin(_ a: URL, _ b: URL) -> Bool {
        func port(_ url: URL) -> Int { url.port ?? (url.scheme?.lowercased() == "https" ? 443 : 80) }
        return a.scheme?.lowercased() == b.scheme?.lowercased() && a.host?.lowercased() == b.host?.lowercased() && port(a) == port(b)
    }
}
