import SwiftUI
import WebKit

@MainActor
final class WorkspaceModel: NSObject, ObservableObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    @Published var server: URL?
    @Published var loading = false
    @Published var loadError: String?
    @Published var message: String?
    @Published var pendingScan: Data?
    @Published var uploading = false
    @Published var sharedFile: SharedFile?
    let webView: WKWebView
    private var scanUserID: Int?
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
        webView.stopLoading(); server = nil; pendingScan = nil; scanUserID = nil; loadError = nil; loading = false
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
        do {
            try checkOrigin()
            let raw = try await webView.callAsyncJavaScript("const r=await fetch('/api/session'); if(!r.ok) return null; return await r.json();", arguments: [:], in: nil, contentWorld: .page)
            guard let session = raw as? [String: Any], let user = session["user"] as? [String: Any], let id = user["id"] as? Int,
                  !(user["must_change_password"] as? Bool ?? false), (user["must_change_password"] as? Int ?? 0) == 0,
                  user["role"] as? String != "tax_agent" || user["permission"] as? String == "read_write" else {
                throw AppError.message("Sign in, complete any password change and use an account with permission to add receipts.")
            }
            scanUserID = id; return true
        } catch { message = error.localizedDescription; return false }
    }
    func uploadScan() async {
        guard !uploading, let data = pendingScan, let userID = scanUserID else { return }
        uploading = true; defer { uploading = false }
        do {
            try checkOrigin()
            let script = """
            try {
                const sessionResponse=await fetch('/api/session');
                if(!sessionResponse.ok) return {ok:false,error:'Cannot check your session. Sign in and retry.'};
                const session=await sessionResponse.json();
                if(!session.user || session.user.id!==expectedUser) return {ok:false,error:'Your signed-in account changed. Sign in to the account that scanned this receipt, then retry.'};
                if(session.user.must_change_password) return {ok:false,error:'Change your temporary password first.'};
                const bytes=Uint8Array.from(atob(encoded), c=>c.charCodeAt(0));
                const form=new FormData();form.append('file',new Blob([bytes],{type:'application/pdf'}),filename);
                const response=await fetch('/api/receipts',{method:'POST',headers:{'X-CSRF-Token':session.csrf},body:form});
                const result=await response.json();
                if(!response.ok) return {ok:false,error:result.error||'Upload failed. Retry when connected.'};
                if(typeof render==='function' && typeof page!=='undefined'){page='receipts';render();}
                return {ok:true,duplicate:!!result.duplicate};
            } catch (_) { return {ok:false,error:'Could not upload. Keep the app open and retry when connected.'}; }
            """
            let result = try await webView.callAsyncJavaScript(script, arguments: ["encoded": data.base64EncodedString(), "expectedUser": userID, "filename": "iPhone-receipt-\(UUID().uuidString).pdf"], in: nil, contentWorld: .page)
            guard let value = result as? [String: Any], value["ok"] as? Bool == true else {
                throw AppError.message((result as? [String: Any])?["error"] as? String ?? "Upload failed. Your scan is available to retry while this app remains open.")
            }
            pendingScan = nil; scanUserID = nil
            message = value["duplicate"] as? Bool == true ? "This receipt is already in your inbox." : "Receipt saved to your inbox. Open it to review the details or read it with AI."
        } catch { message = error.localizedDescription }
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
