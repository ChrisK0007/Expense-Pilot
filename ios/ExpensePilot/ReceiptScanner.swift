import SwiftUI
import VisionKit
import UIKit

struct ReceiptScanner: UIViewControllerRepresentable {
    var onResult: (Result<Data, Error>) -> Void
    var onCancel: () -> Void
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> VNDocumentCameraViewController {
        let camera = VNDocumentCameraViewController(); camera.delegate = context.coordinator; return camera
    }
    func updateUIViewController(_ controller: VNDocumentCameraViewController, context: Context) {}
    final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate {
        let parent: ReceiptScanner
        init(_ parent: ReceiptScanner) { self.parent = parent }
        func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) { parent.onCancel() }
        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFailWithError error: Error) { parent.onResult(.failure(error)) }
        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFinishWith scan: VNDocumentCameraScan) {
            guard (1...8).contains(scan.pageCount) else { parent.onResult(.failure(AppError.message("Scan 1–8 pages per receipt."))); return }
            let bounds = CGRect(x: 0, y: 0, width: 595, height: 842)
            let data = UIGraphicsPDFRenderer(bounds: bounds).pdfData { renderer in
                for index in 0..<scan.pageCount {
                    let image = scan.imageOfPage(at: index)
                    let scale = min(1, 1800 / max(image.size.width, image.size.height))
                    let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
                    let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.opaque = true
                    let small = UIGraphicsImageRenderer(size: size, format: format).image { _ in image.draw(in: CGRect(origin: .zero, size: size)) }
                    let compressed = small.jpegData(compressionQuality: 0.75).flatMap(UIImage.init(data:)) ?? small
                    renderer.beginPage()
                    let ratio = min(575 / size.width, 822 / size.height)
                    let target = CGSize(width: size.width * ratio, height: size.height * ratio)
                    compressed.draw(in: CGRect(x: (595-target.width)/2, y: (842-target.height)/2, width: target.width, height: target.height))
                }
            }
            guard data.count <= 11 * 1024 * 1024 else { parent.onResult(.failure(AppError.message("This scan is too large. Scan fewer pages at a time."))); return }
            parent.onResult(.success(data))
        }
    }
}
struct SharedFile: Identifiable { let id = UUID(); let url: URL }
struct ShareFile: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: [url], applicationActivities: nil) }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
