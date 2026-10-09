import SwiftUI
import WebKit

@MainActor
final class WorkspaceModel: NSObject, ObservableObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    @Published var server: URL?
    @Published var loading = false
    @Published var loadError: String?
    @Published var message: String?
    @Published private(set) var pendingScan: Data?
    @Published var checkingScan = false
    @Published var uploading = false
    @Published var sharedFile: SharedFile?
    let webView: WKWebView
    private var scanUserID: Int?
    private var scanServer: URL?
    private var scanID: UUID?
    private var workspaceID = UUID()
    private var downloads: [ObjectIdentifier: URL] = [:]
    private let shareDirectory = FileManager.default.temporaryDirectory.appendingPathComponent("ExpensePilotExports", isDirectory: true)

    override init() {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        webView = WKWebView(frame: .zero, configuration: configuration)
        super.init()
        webView.navigationDelegate = self; webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.keyboardDismissMode = .interactive
        try? FileManager.default.removeItem(at: shareDirectory)
        if let stored = UserDefaults.standard.string(forKey: "server"), let url = try? ServerAddress.parse(stored, allowLocalHTTP: true) {
            server = url; reload()
        }
    }
    func connect(_ url: URL) async {
        if server != url { await disconnect() }
        server = url; UserDefaults.standard.set(url.absoluteString, forKey: "server"); reload()
    }
    func disconnect() async {
        workspaceID = UUID()
        webView.stopLoading(); server = nil; discardScan(); uploading = false; loadError = nil; loading = false
        UserDefaults.standard.removeObject(forKey: "server")
        webView.loadHTMLString("", baseURL: nil)
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            webView.configuration.websiteDataStore.removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast) { continuation.resume() }
        }
        try? FileManager.default.removeItem(at: shareDirectory)
    }
    func reload() {
        guard let server else { return }
        loadError = nil; loading = true
        webView.load(URLRequest(url: server, cachePolicy: .reloadIgnoringLocalCacheData))
    }
    private func checkOrigin() throws {
        guard let server, let current = webView.url, ServerAddress.sameOrigin(server, current) else { throw AppError.message("Open your Expense Pilot workspace before scanning or uploading.") }
    }
    func canScan() async -> Bool {
        guard !checkingScan, !uploading, pendingScan == nil else { return false }
        checkingScan = true; defer { checkingScan = false }
        let workspace = workspaceID
        do {
            try checkOrigin()
            // The camera itself does not need the network. This snapshot only binds
            // the local scan; uploadScan checks the live account and permissions.
            let raw = try await webView.callAsyncJavaScript(ReceiptBridge.scanContext, arguments: [:], in: nil, contentWorld: .page)
            guard workspace == workspaceID else { return false }
            guard let result = raw as? [String: Any], result["ok"] as? Bool == true,
                  let id = result["userID"] as? Int else {
                message = (raw as? [String: Any])?["error"] as? String ?? "Reconnect and load your signed-in workspace before scanning."
                return false
            }
            try checkOrigin()
            scanUserID = id; scanServer = server; scanID = UUID()
            return true
        } catch {
            if workspace == workspaceID {
                message = "Load your Expense Pilot workspace and sign in while connected before scanning. If the connection drops afterwards, you can still scan and retry the upload when reconnected."
            }
            return false
        }
    }
    func keepScan(_ data: Data) {
        guard scanID != nil, scanUserID != nil, scanServer == server else {
            message = "The server changed while scanning. Open your workspace and scan again."
            return
        }
        pendingScan = data
    }
    func discardScan() {
        pendingScan = nil; scanUserID = nil; scanServer = nil; scanID = nil
    }
    func uploadScan() async {
        guard !uploading, let data = pendingScan, let userID = scanUserID, let attempt = scanID else { return }
        uploading = true
        defer { if scanID == attempt { uploading = false } }
        do {
            guard server == scanServer else { throw AppError.message("Reconnect to the server where this receipt was scanned, then retry.") }
            try checkOrigin()
            let result = try await webView.callAsyncJavaScript(ReceiptBridge.uploadScan, arguments: ["encoded": data.base64EncodedString(), "expectedUser": userID, "filename": "iPhone-receipt-\(attempt.uuidString).pdf"], in: nil, contentWorld: .page)
            guard scanID == attempt else { return }
            guard let value = result as? [String: Any], value["ok"] as? Bool == true else {
                message = (result as? [String: Any])?["error"] as? String ?? "Upload could not finish. Keep the app open, reconnect and retry. Your scan is still available."
                return
            }
            discardScan(); uploading = false
            message = value["duplicate"] as? Bool == true ? "This receipt is already in your inbox." : "Receipt saved to your inbox. Open it to review the details or read it with AI."
        } catch {
            if scanID == attempt {
                message = "Upload could not finish. Keep the app open, reconnect and reload your workspace if needed, then tap Retry upload. Your scan is still available."
            }
        }
    }
    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) { loading = true; loadError = nil }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { loading = false }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { failed(error) }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { failed(error) }
    private func failed(_ error: Error) {
        loading = false
        if (error as NSError).code != NSURLErrorCancelled { loadError = "Check that your server is running and reachable over Wi-Fi, VPN or HTTPS. \(error.localizedDescription)" }
    }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { loadError = "The workspace was interrupted. Reload to continue."; loading = false }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url, let server else { decisionHandler(.cancel); return }
        if ServerAddress.sameOrigin(url, server) {
            decisionHandler(action.shouldPerformDownload ? .download : .allow); return
        }
        if url.scheme == "blob", url.absoluteString.hasPrefix("blob:" + server.absoluteString.dropLast()), let current = webView.url, ServerAddress.sameOrigin(current, server) {
            decisionHandler(action.shouldPerformDownload ? .download : .allow); return
        }
        decisionHandler(.cancel)
        if action.navigationType == .linkActivated, ["https", "mailto", "tel"].contains(url.scheme?.lowercased() ?? "") { UIApplication.shared.open(url) }
        else { loading = false; message = "This page redirects outside your configured server. Use a server address that opens Expense Pilot directly, or connect over your VPN." }
    }
    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let disposition = (response.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition") ?? ""
        decisionHandler(!response.canShowMIMEType || disposition.lowercased().contains("attachment") ? .download : .allow)
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        do {
            try FileManager.default.createDirectory(at: shareDirectory, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.complete])
            let safeName = URL(fileURLWithPath: suggestedFilename).lastPathComponent
            let destination = shareDirectory.appendingPathComponent(UUID().uuidString + "-" + (safeName.isEmpty ? "export" : safeName))
            downloads[ObjectIdentifier(download)] = destination; completionHandler(destination)
        } catch { completionHandler(nil); message = error.localizedDescription }
    }
    func downloadDidFinish(_ download: WKDownload) {
        if let url = downloads.removeValue(forKey: ObjectIdentifier(download)) { sharedFile = SharedFile(url: url) }
        loading = false
    }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        if let url = downloads.removeValue(forKey: ObjectIdentifier(download)) { try? FileManager.default.removeItem(at: url) }
        loading = false; message = error.localizedDescription
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url, let server, ServerAddress.sameOrigin(url, server) { webView.load(action.request) }
        else if let url = action.request.url, url.scheme == "https" { UIApplication.shared.open(url) }
        return nil
    }
    private func present(_ alert: UIAlertController) {
        var presenter = webView.window?.rootViewController
        while let next = presenter?.presentedViewController { presenter = next }
        presenter?.present(alert, animated: true)
    }
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage text: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = UIAlertController(title: "Expense Pilot", message: text, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() }); present(alert)
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage text: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = UIAlertController(title: "Expense Pilot", message: text, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(false) })
        alert.addAction(UIAlertAction(title: "Continue", style: .default) { _ in completionHandler(true) }); present(alert)
    }
    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let alert = UIAlertController(title: "Expense Pilot", message: prompt, preferredStyle: .alert)
        alert.addTextField { $0.text = defaultText }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(nil) })
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(alert.textFields?.first?.text) }); present(alert)
    }
}
struct WorkspaceWebView: UIViewRepresentable {
    @ObservedObject var model: WorkspaceModel
    func makeUIView(context: Context) -> WKWebView { model.webView }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
