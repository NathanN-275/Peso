import Foundation

enum PrivateExportError: LocalizedError {
    case unavailable

    var errorDescription: String? { "Unable to complete private export file handling." }
}

final class PrivateExportStore {
    private final class Entry {
        let owner: UUID
        let id = UUID().uuidString.lowercased()
        var started = false
        var canceled = false
        var abandoned = false
        var transfer: PrivateExportDownload?

        init(owner: UUID) { self.owner = owner }
    }

    private let lock = NSLock()
    private var entry: Entry?
    private var preparedOwner: UUID?
    private let root: URL

    init(root: URL = URL.cachesDirectory.appendingPathComponent("peso-private-export-v1", isDirectory: true)) {
        self.root = root
    }

    private func directory(_ entry: Entry) -> URL {
        root.appendingPathComponent(entry.id, isDirectory: true)
    }

    private func delete(_ path: URL) throws {
        do {
            try FileManager.default.removeItem(at: path)
        } catch let error as CocoaError where error.code == .fileNoSuchFile || error.code == .fileReadNoSuchFile {
            return
        } catch {
            throw PrivateExportError.unavailable
        }
    }

    func purgeOnStartup(owner: UUID) throws {
        lock.lock()
        defer { lock.unlock() }
        if preparedOwner == owner { return }
        guard entry == nil else { throw PrivateExportError.unavailable }
        try delete(root)
        preparedOwner = owner
    }

    func reserve(owner: UUID) throws -> String {
        lock.lock()
        defer { lock.unlock() }
        guard preparedOwner == owner, entry == nil else { throw PrivateExportError.unavailable }
        let next = Entry(owner: owner)
        entry = next
        return next.id
    }

    func cancel(owner: UUID, id: String) {
        lock.lock()
        defer { lock.unlock() }
        guard let entry, entry.owner == owner, entry.id == id else { return }
        entry.canceled = true
        entry.transfer?.cancel()
    }

    func remove(owner: UUID, id: String) throws {
        lock.lock()
        defer { lock.unlock() }
        guard let entry, entry.owner == owner, entry.id == id, entry.transfer == nil else {
            throw PrivateExportError.unavailable
        }
        try delete(directory(entry))
        self.entry = nil
    }

    func abandon(owner: UUID) {
        lock.lock()
        defer { lock.unlock() }
        if preparedOwner == owner { preparedOwner = nil }
        guard let entry, entry.owner == owner else { return }
        entry.abandoned = true
        entry.canceled = true
        if let transfer = entry.transfer {
            transfer.cancel()
        } else {
            discardAbandoned(entry)
        }
    }

    private func discardAbandoned(_ entry: Entry) {
        // A failed deletion is retried by purgeOnStartup before another session.
        try? delete(directory(entry))
        self.entry = nil
    }

    func download(owner: UUID, id: String, request: URLRequest, done: @escaping (URL?) -> Void) throws {
        lock.lock()
        defer { lock.unlock() }
        guard let entry, entry.owner == owner, entry.id == id, !entry.canceled, !entry.started else {
            throw PrivateExportError.unavailable
        }
        entry.started = true
        let destination = directory(entry)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let rootInfo = try root.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard rootInfo.isDirectory == true, rootInfo.isSymbolicLink == false else {
            throw PrivateExportError.unavailable
        }
        try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: false)
        let transfer = PrivateExportDownload(request: request, directory: destination) { [self] result in
            lock.lock()
            entry.transfer = nil
            let accepted = entry.canceled ? nil : result
            if entry.abandoned { discardAbandoned(entry) }
            lock.unlock()
            done(accepted)
        }
        entry.transfer = transfer
        transfer.start()
    }
}

final class PrivateExportDownload: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
    private let directory: URL
    private let done: (URL?) -> Void
    private var session: URLSession!
    private var task: URLSessionDownloadTask!
    // URLSession serializes callbacks on its delegate queue.
    private var output: URL?

    static func request(url: String, grant: String) throws -> URLRequest {
        let id = "[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
        let path = "^/private-media/video/(?!00000000-0000-0000-0000-000000000000/)\(id)/export%3A(clean|pose|barbell|pose-barbell)$"
        guard let parts = URLComponents(string: url), parts.scheme == "https",
              let host = parts.host, host == "usepeso.com" || host.hasSuffix(".usepeso.com"),
              parts.port == nil, parts.user == nil, parts.password == nil,
              parts.query == nil, parts.fragment == nil,
              parts.percentEncodedPath.range(of: path, options: .regularExpression) != nil,
              let target = parts.url,
              grant.utf8.count == 43,
              grant.range(of: "^[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]$", options: .regularExpression) != nil else {
            throw PrivateExportError.unavailable
        }
        var request = URLRequest(url: target, cachePolicy: .reloadIgnoringLocalCacheData)
        request.setValue(grant, forHTTPHeaderField: "X-Peso-Media-Grant")
        request.setValue("identity", forHTTPHeaderField: "Accept-Encoding")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        return request
    }

    init(request: URLRequest, directory: URL, done: @escaping (URL?) -> Void) {
        self.directory = directory
        self.done = done
        super.init()
        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil
        config.urlCredentialStorage = nil
        config.httpCookieStorage = nil
        config.httpShouldSetCookies = false
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 135
        session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
        task = session.downloadTask(with: request)
    }

    func start() { task.resume() }

    func cancel() { task.cancel() }

    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }

    private func metadata(_ response: URLResponse?) -> (length: Int64, extension: String)? {
        let types = ["video/mp4": "mp4", "video/quicktime": "mov", "video/x-m4v": "m4v",
                     "video/m4v": "m4v", "video/webm": "webm", "video/x-matroska": "mkv"]
        guard let http = response as? HTTPURLResponse, http.statusCode == 200,
              let mime = http.mimeType, let ext = types[mime],
              let declared = http.value(forHTTPHeaderField: "Content-Length"), let length = Int64(declared),
              length > 0, length == http.expectedContentLength, String(length) == declared,
              http.value(forHTTPHeaderField: "Content-Range") == nil,
              http.value(forHTTPHeaderField: "Transfer-Encoding") == nil,
              let cache = http.value(forHTTPHeaderField: "Cache-Control") else { return nil }
        let encoding = http.value(forHTTPHeaderField: "Content-Encoding")?.lowercased()
        guard encoding == nil || encoding == "identity" else { return nil }
        let directives = cache.lowercased().split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
        guard directives.contains("private"), directives.contains("no-store") else { return nil }
        return (length, ext)
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didWriteData bytesWritten: Int64,
                    totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        guard let expected = metadata(downloadTask.response), totalBytesWritten <= expected.length else {
            downloadTask.cancel()
            return
        }
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        guard let expected = metadata(downloadTask.response),
              let bytes = try? location.resourceValues(forKeys: [.fileSizeKey]).fileSize,
              Int64(bytes) == expected.length else { return }
        let target = directory.appendingPathComponent("asset." + expected.extension)
        do {
            try FileManager.default.moveItem(at: location, to: target)
            output = target
        } catch {
            // The caller removes the operation directory after settlement.
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        session.finishTasksAndInvalidate()
        done(error == nil ? output : nil)
    }
}
