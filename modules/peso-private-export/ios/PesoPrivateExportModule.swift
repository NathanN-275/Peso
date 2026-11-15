import ExpoModulesCore
import Foundation

public final class PesoPrivateExportModule: Module {
    private let owner = UUID()
    private static let exports = PrivateExportStore()

    public func definition() -> ModuleDefinition {
        Name("PesoPrivateExport")

        Function("purgeOnStartup") {
            try Self.exports.purgeOnStartup(owner: self.owner)
        }

        Function("reserve") {
            try Self.exports.reserve(owner: self.owner)
        }

        Function("cancel") { (id: String) in
            Self.exports.cancel(owner: self.owner, id: id)
        }

        Function("remove") { (id: String) in
            try Self.exports.remove(owner: self.owner, id: id)
        }

        AsyncFunction("download") { (id: String, url: String, grant: String, promise: Promise) in
            do {
                let request = try PrivateExportDownload.request(url: url, grant: grant)
                try Self.exports.download(owner: self.owner, id: id, request: request) { result in
                    if let result {
                        promise.resolve(result.absoluteString)
                    } else {
                        promise.reject("ERR_PRIVATE_EXPORT", "Unable to download the private video.")
                    }
                }
            } catch {
                promise.reject("ERR_PRIVATE_EXPORT", "Unable to download the private video.")
            }
        }

        OnDestroy {
            Self.exports.abandon(owner: self.owner)
        }
    }
}
