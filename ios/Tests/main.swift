import Foundation
func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}
for text in ["https://expenses.example.com", "https://expenses.example.com:443/", "http://192.168.3.25:8788", "http://10.0.0.2:8788", "http://172.16.1.2", "http://enterprise.local:8788"] {
    _ = try ServerAddress.parse(text, allowLocalHTTP: true)
}
for text in ["http://example.com", "http://10.0.0.2.evil.com", "http://172.32.1.2", "https://user:password@example.com", "javascript:alert(1)", "file:///tmp/test", "https://example.com/login", "https://example.com?token=secret", "https://example.com#fragment"] {
    do { _ = try ServerAddress.parse(text, allowLocalHTTP: true); fatalError("Accepted invalid address: \(text)") } catch {}
}
do { _ = try ServerAddress.parse("http://192.168.3.25", allowLocalHTTP: false); fatalError("HTTP did not require consent") } catch {}
let a = URL(string: "https://example.com")!, b = URL(string: "https://example.com:443/api/session")!
check(ServerAddress.sameOrigin(a,b), "Default HTTPS port should match")
check(!ServerAddress.sameOrigin(a,URL(string:"https://example.com.evil.test")!), "Host isolation failed")
check(!ServerAddress.sameOrigin(a,URL(string:"http://example.com")!), "Scheme isolation failed")
check(!ServerAddress.sameOrigin(a,URL(string:"https://example.com:8443")!), "Port isolation failed")
print("PASS: server address validation, local HTTP opt-in and origin isolation")
