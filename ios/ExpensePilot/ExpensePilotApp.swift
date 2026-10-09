import SwiftUI
import VisionKit

@main
struct ExpensePilotApp: App {
    @StateObject private var workspace = WorkspaceModel()
    var body: some Scene {
        WindowGroup { RootView().environmentObject(workspace).tint(Color(red: 0.39, green: 0.31, blue: 0.91)) }
    }
}

struct RootView: View {
    @EnvironmentObject var model: WorkspaceModel
    @State private var configure = false
    @State private var scan = false
    @State private var askDisconnect = false

    var body: some View {
        NavigationStack {
            Group {
                if model.server != nil {
                    VStack(spacing: 0) {
                        if model.loading { ProgressView().frame(maxWidth: .infinity).padding(4) }
                        if let error = model.loadError {
                            ContentUnavailableView {
                                Label("Cannot reach Expense Pilot", systemImage: "wifi.exclamationmark")
                            } description: { Text(error) } actions: {
                                Button("Try again") { model.reload() }
                                Button("Server settings") { configure = true }
                            }
                        } else { WorkspaceWebView(model: model) }
                        if model.pendingScan != nil {
                            HStack {
                                Text(model.uploading ? "Uploading receipt…" : "Scanned receipt ready to upload").font(.caption)
                                Spacer()
                                Button("Retry upload") { Task { await model.uploadScan() } }.disabled(model.uploading)
                                Button("Discard", role: .destructive) { model.pendingScan = nil }.disabled(model.uploading)
                            }.padding(10).background(.thinMaterial)
                        }
                    }
                } else {
                    ContentUnavailableView {
                        Label("Expense Pilot", systemImage: "paperplane.fill")
                    } description: {
                        Text("a clearer view of every dollar\n\nConnect to your Expense Pilot server to get started.")
                    } actions: { Button("Connect to server") { configure = true }.buttonStyle(.borderedProminent) }
                }
            }
            .navigationTitle("Expense Pilot")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Menu {
                        Button("Server settings", systemImage: "server.rack") { configure = true }
                        Button("Reload workspace", systemImage: "arrow.clockwise") { model.reload() }.disabled(model.uploading)
                        if model.server != nil { Button("Disconnect & clear this device", systemImage: "rectangle.portrait.and.arrow.right", role: .destructive) { askDisconnect = true } }
                    } label: { Image(systemName: "gearshape") }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { if await model.canScan() { scan = true } } } label: { Label("Scan receipt", systemImage: "doc.viewfinder") }
                        .disabled(model.server == nil || model.loading || model.uploading || model.pendingScan != nil || !VNDocumentCameraViewController.isSupported)
                }
            }
            .sheet(isPresented: $configure) { ServerSettings().environmentObject(model) }
            .sheet(isPresented: $scan) {
                ReceiptScanner { result in
                    scan = false
                    switch result {
                    case .success(let data): model.pendingScan = data; Task { await model.uploadScan() }
                    case .failure(let error): model.message = error.localizedDescription
                    }
                } onCancel: { scan = false }
                .ignoresSafeArea()
            }
            .alert("Expense Pilot", isPresented: Binding(get: { model.message != nil }, set: { if !$0 { model.message = nil } })) {
                Button("OK") { model.message = nil }
            } message: { Text(model.message ?? "") }
            .confirmationDialog("Clear this iPhone’s session and server address? Unsaved scans will be discarded. Server records stay intact.", isPresented: $askDisconnect, titleVisibility: .visible) {
                Button("Disconnect", role: .destructive) { Task { await model.disconnect() } }
            }
            .sheet(item: $model.sharedFile) { item in ShareFile(url: item.url) }
        }
    }
}

struct ServerSettings: View {
    @EnvironmentObject var model: WorkspaceModel
    @Environment(\.dismiss) private var dismiss
    @State private var address = ""
    @State private var allowLocal = false
    @State private var error: String?
    @State private var connecting = false
    var body: some View {
        NavigationStack {
            Form {
                Section("Your Expense Pilot server") {
                    TextField("https://expenses.example.com", text: $address).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Toggle("Allow HTTP on my local network", isOn: $allowLocal)
                    Text("Use HTTPS when away from home. Local HTTP sends your login and records without transport encryption; use it only on your trusted network.").font(.footnote).foregroundStyle(.secondary)
                }
                Section {
                    Button("Connect") {
                        do {
                            let url = try ServerAddress.parse(address, allowLocalHTTP: allowLocal)
                            connecting = true
                            Task { await model.connect(url); connecting = false; dismiss() }
                        } catch { self.error = error.localizedDescription }
                    }.disabled(connecting || model.uploading)
                    if let error { Text(error).foregroundStyle(.red) }
                } footer: { Text("Changing servers clears this app’s saved sign-in. Use your existing Expense Pilot login and authenticator code. This build requires a network connection; GPS tracking and offline sync are not included yet.") }
                Section("Development build") {
                    Text("iPhone app 0.1.0 · Expense Pilot server 0.8.0 or later")
                    Text("Free Xcode signing expires after about seven days. Re-run from Xcode using the same bundle identifier to renew without deleting the app.").font(.footnote)
                }
            }.navigationTitle("Server settings").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } } }
            .onAppear { address = model.server?.absoluteString ?? ""; allowLocal = model.server?.scheme == "http" }
        }
    }
}
