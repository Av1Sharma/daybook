import Foundation
import CryptoKit
import Darwin

struct UpdateFailure: LocalizedError {
    let message: String
    var errorDescription: String? { message }
    init(_ message: String) { self.message = message }
}
struct AppVersion: Comparable, Equatable {
    let components: [Int]
    init(_ string: String) throws {
        let parts = string.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 3, parts.allSatisfy({ !$0.isEmpty && $0.allSatisfy({ $0.isASCII && $0.isNumber }) }),
              parts.allSatisfy({ Int($0).map { $0 >= 0 && $0 < 1_000_000 } ?? false }) else { throw UpdateFailure("The release version is not supported.") }
        components = parts.map { Int($0)! }
    }
    static func < (lhs: Self, rhs: Self) -> Bool { lhs.components.lexicographicallyPrecedes(rhs.components) }
}
struct UpdateManifest: Codable {
    let version: String
    let minimumSystemVersion: String
    let archive: String
    let sha256: String
    let size: Int
}
struct ReleaseInfo: Decodable {
    let tag_name: String
    let draft: Bool
    let prerelease: Bool
}
struct UpdateCandidate {
    let manifest: UpdateManifest
    let tag: String
    let folder: URL
}

enum UpdateSecurity {
    static let repository = "Av1Sharma/daybook"
    static let archiveName = "Daybook-update.zip"
    static let manifestName = "daybook-update.json"
    static let signatureName = "daybook-update.sig"
    static let bundleID = "com.avisharma.daybook"
    static func manifest(_ data: Data, signature: Data, publicKey: String = daybookUpdatePublicKey) throws -> UpdateManifest {
        guard data.count <= 65536, signature.count <= 256,
              let keyBytes = Data(base64Encoded: publicKey),
              let signatureText = String(data: signature, encoding: .utf8),
              let signatureBytes = Data(base64Encoded: signatureText.trimmingCharacters(in: .whitespacesAndNewlines)),
              let key = try? Curve25519.Signing.PublicKey(rawRepresentation: keyBytes),
              key.isValidSignature(signatureBytes, for: data) else { throw UpdateFailure("The update signature is invalid. Nothing has been installed.") }
        let result = try JSONDecoder().decode(UpdateManifest.self, from: data)
        _ = try AppVersion(result.version)
        _ = try AppVersion(result.minimumSystemVersion)
        guard result.archive == archiveName, result.size > 0, result.size <= 32 * 1024 * 1024,
              result.sha256.count == 64, result.sha256.allSatisfy({ "0123456789abcdef".contains($0) }) else { throw UpdateFailure("The signed update information is invalid.") }
        return result
    }
    static func verifyArchive(_ url: URL, manifest: UpdateManifest) throws {
        let attrs = try FileManager.default.attributesOfItem(atPath: url.path)
        guard (attrs[.size] as? NSNumber)?.intValue == manifest.size else { throw UpdateFailure("The update download is incomplete or has the wrong size.") }
        let data = try Data(contentsOf: url, options: .mappedIfSafe)
        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard digest == manifest.sha256 else { throw UpdateFailure("The update download did not pass its integrity check.") }
    }
    static func validateArchivePaths(_ listing: String) throws {
        let paths = listing.split(separator: "\n").map(String.init)
        guard !paths.isEmpty, paths.count <= 5000 else { throw UpdateFailure("The update archive is empty or too large.") }
        for path in paths {
            let pieces = path.split(separator: "/", omittingEmptySubsequences: false)
            guard path == "Daybook.app/" || path.hasPrefix("Daybook.app/"), !path.hasPrefix("/"), !path.contains("\\"),
                  !pieces.contains(".."), !pieces.contains("."), !path.contains("\r") else { throw UpdateFailure("The update contains an unsafe file path.") }
        }
    }
    static func validateBundle(_ app: URL, version: String) throws {
        let values = try app.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard values.isDirectory == true, values.isSymbolicLink != true,
              let plistData = try? Data(contentsOf: app.appendingPathComponent("Contents/Info.plist")),
              let plist = try? PropertyListSerialization.propertyList(from:plistData,format:nil) as? [String:Any],
              plist["CFBundleIdentifier"] as? String == bundleID,
              plist["CFBundleShortVersionString"] as? String == version,
              plist["CFBundleExecutable"] as? String == "Daybook" else { throw UpdateFailure("The downloaded app is not the expected Daybook version.") }
        if let items = FileManager.default.enumerator(at: app, includingPropertiesForKeys: [.isSymbolicLinkKey]) {
            for case let item as URL in items {
                if try item.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink == true { throw UpdateFailure("Unexpected links were found in the update bundle.") }
            }
        }
        _ = try UpdateProcess.run("/usr/bin/codesign", ["--verify", "--deep", "--strict", app.path], timeout: 30)
    }
}

enum UpdateProcess {
    // Arguments are passed directly to the executable, never to a shell. Output goes to a private file to avoid pipe deadlocks.
    static func run(_ executable: String, _ arguments: [String], timeout: TimeInterval = 90) throws -> Data {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("DaybookCommand-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: folder) }
        let output = folder.appendingPathComponent("output")
        FileManager.default.createFile(atPath: output.path, contents: nil, attributes: [.posixPermissions: 0o600])
        let handle = try FileHandle(forWritingTo: output)
        defer { try? handle.close() }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.standardOutput = handle
        // Don't surface credential-service output or HTTP diagnostics in the app.
        process.standardError = FileHandle.nullDevice
        process.standardInput = FileHandle.nullDevice
        var env = ProcessInfo.processInfo.environment
        for key in ["GH_DEBUG", "DEBUG", "GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "GH_REPO", "GIT_TRACE", "GIT_CURL_VERBOSE"] { env.removeValue(forKey: key) }
        env["GH_PROMPT_DISABLED"] = "1"; env["GH_NO_UPDATE_NOTIFIER"] = "1"; env["GH_HOST"] = "github.com"
        process.environment = env
        let finished = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in finished.signal() }
        try process.run()
        if finished.wait(timeout: .now() + timeout) == .timedOut {
            process.terminate()
            if finished.wait(timeout: .now() + 2) == .timedOut { kill(process.processIdentifier, SIGKILL); process.waitUntilExit() }
            throw UpdateFailure("The update request timed out. Try again when your connection is available.")
        }
        guard process.terminationStatus == 0 else { throw UpdateFailure("The update request failed. Check your connection and GitHub sign-in, then try again.") }
        let size = (try FileManager.default.attributesOfItem(atPath: output.path)[.size] as? NSNumber)?.intValue ?? 0
        guard size <= 2 * 1024 * 1024 else { throw UpdateFailure("The update response was unexpectedly large.") }
        return try Data(contentsOf: output)
    }
}

enum GitHubUpdates {
    static func cli() throws -> String {
        for path in ["/opt/homebrew/bin/gh", "/usr/local/bin/gh", "/usr/bin/gh"] {
            if FileManager.default.isExecutableFile(atPath: path) { return path }
        }
        throw UpdateFailure("Private updates need GitHub CLI. Install it from cli.github.com, sign in with gh auth login, then check again. Daybook never stores your GitHub token.")
    }
    static func latest(current: String) throws -> UpdateCandidate? {
        let tool = try cli()
        let data: Data
        do { data = try UpdateProcess.run(tool, ["api", "repos/" + UpdateSecurity.repository + "/releases/latest", "--hostname", "github.com"]) }
        catch { throw UpdateFailure("Couldn’t read the private Daybook releases. Check your internet connection and sign in with gh auth login using the GitHub account that can access Av1Sharma/daybook.") }
        let release = try JSONDecoder().decode(ReleaseInfo.self, from: data)
        guard !release.draft, !release.prerelease, release.tag_name.hasPrefix("v") else { return nil }
        let version = String(release.tag_name.dropFirst())
        guard try AppVersion(version) > AppVersion(current) else { return nil }
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("DaybookUpdate-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        do {
            _ = try UpdateProcess.run(tool, ["release", "download", release.tag_name, "--repo", "github.com/" + UpdateSecurity.repository, "--pattern", UpdateSecurity.manifestName, "--pattern", UpdateSecurity.signatureName, "--dir", folder.path])
            let manifest = try UpdateSecurity.manifest(Data(contentsOf: folder.appendingPathComponent(UpdateSecurity.manifestName)), signature: Data(contentsOf: folder.appendingPathComponent(UpdateSecurity.signatureName)))
            guard manifest.version == version else { throw UpdateFailure("The release version does not match its signed update information.") }
            let os = ProcessInfo.processInfo.operatingSystemVersion
            guard try AppVersion("\(os.majorVersion).\(os.minorVersion).\(os.patchVersion)") >= AppVersion(manifest.minimumSystemVersion) else { throw UpdateFailure("This update requires macOS " + manifest.minimumSystemVersion + " or later.") }
            return UpdateCandidate(manifest: manifest, tag: release.tag_name, folder: folder)
        } catch { try? FileManager.default.removeItem(at: folder); throw error }
    }
    static func prepare(_ candidate: UpdateCandidate) throws -> URL {
        let archive = candidate.folder.appendingPathComponent(UpdateSecurity.archiveName)
        if FileManager.default.fileExists(atPath: archive.path) { try FileManager.default.removeItem(at: archive) }
        _ = try UpdateProcess.run(cli(), ["release", "download", candidate.tag, "--repo", "github.com/" + UpdateSecurity.repository, "--pattern", UpdateSecurity.archiveName, "--dir", candidate.folder.path], timeout: 180)
        try UpdateSecurity.verifyArchive(archive, manifest: candidate.manifest)
        let listing = try UpdateProcess.run("/usr/bin/unzip", ["-Z1", archive.path])
        try UpdateSecurity.validateArchivePaths(String(decoding: listing, as: UTF8.self))
        let extracted = candidate.folder.appendingPathComponent("extracted")
        if FileManager.default.fileExists(atPath: extracted.path) { try FileManager.default.removeItem(at: extracted) }
        try FileManager.default.createDirectory(at: extracted, withIntermediateDirectories: false)
        _ = try UpdateProcess.run("/usr/bin/ditto", ["-x", "-k", archive.path, extracted.path])
        let app = extracted.appendingPathComponent("Daybook.app")
        try UpdateSecurity.validateBundle(app, version: candidate.manifest.version)
        return app
    }
}
