import Foundation
import CryptoKit

@main
struct UpdaterTests {
    static func main() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("DaybookTests-" + UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        var checks = 0
        func expect(_ condition: Bool, _ label: String) {
            precondition(condition, label); checks += 1
        }
        func rejects(_ label: String, _ body: () throws -> Void) {
            do { try body(); fatalError("Expected rejection: " + label) } catch { checks += 1 }
        }
        expect(try AppVersion("1.10.0") > AppVersion("1.2.9"), "Numeric version order")
        for value in ["1.2", "v1.2.0", "1.2.-1", "1.2.0-beta", "1..0", "1000000.0.0"] {
            rejects("Malformed version") { _ = try AppVersion(value) }
        }
        let key = Curve25519.Signing.PrivateKey()
        let publicKey = key.publicKey.rawRepresentation.base64EncodedString()
        let payload = Data("test archive".utf8)
        let digest = SHA256.hash(data: payload).map { String(format: "%02x", $0) }.joined()
        let manifest = UpdateManifest(version: "1.2.0", minimumSystemVersion: "13.0.0", archive: UpdateSecurity.archiveName, sha256: digest, size: payload.count)
        let bytes = try JSONEncoder().encode(manifest)
        let signature = Data(try key.signature(for: bytes).base64EncodedString().utf8)
        expect(try UpdateSecurity.manifest(bytes, signature: signature, publicKey: publicKey).version == "1.2.0", "Valid signature")
        rejects("Tampered manifest") { _ = try UpdateSecurity.manifest(bytes + Data(" ".utf8), signature: signature, publicKey: publicKey) }
        rejects("Wrong signing key") { _ = try UpdateSecurity.manifest(bytes, signature: signature) }
        let archive = root.appendingPathComponent("archive.zip")
        try payload.write(to: archive)
        try UpdateSecurity.verifyArchive(archive, manifest: manifest); checks += 1
        try Data(repeating: 65, count: payload.count).write(to: archive)
        rejects("Same-size corruption") { try UpdateSecurity.verifyArchive(archive, manifest: manifest) }
        try Data().write(to: archive)
        rejects("Truncated download") { try UpdateSecurity.verifyArchive(archive, manifest: manifest) }
        try UpdateSecurity.validateArchivePaths("Daybook.app/\nDaybook.app/Contents/Info.plist\n"); checks += 1
        for path in ["Daybook.app/../outside", "/Daybook.app/file", "Other.app/file", "Daybook.app/./file", "Daybook.app/evil\\path", ""] {
            rejects("Unsafe ZIP path") { try UpdateSecurity.validateArchivePaths(path) }
        }
        let notebook = root.appendingPathComponent("notebook.json")
        let notebookBytes = Data("personal notebook sentinel".utf8)
        try notebookBytes.write(to: notebook)
        func fixture(_ name: String) throws -> InstallJob {
            let parent = root.appendingPathComponent(name)
            try fm.createDirectory(at: parent, withIntermediateDirectories: true)
            let dest = parent.appendingPathComponent("Daybook.app"), stage = parent.appendingPathComponent(".Daybook.update-test.app")
            for (url, version) in [(dest, "1.1.0"), (stage, "1.2.0")] {
                try fm.createDirectory(at: url, withIntermediateDirectories: true)
                try Data(version.utf8).write(to: url.appendingPathComponent("version"))
            }
            return InstallJob(destination: dest.path, staged: stage.path, backup: parent.appendingPathComponent(".Daybook.previous-test.app").path, parentPID: 12345, previousVersion: "1.1.0", version: "1.2.0", resultFile: parent.appendingPathComponent("result.json").path, dataDirectory: nil)
        }
        func validate(_ app: URL, _ version: String) throws {
            guard try String(contentsOf: app.appendingPathComponent("version"), encoding: .utf8) == version else { throw UpdateFailure("Wrong fixture version") }
        }
        let success = try fixture("success")
        try AppInstaller.replace(success, validate: validate) { try validate($0, "1.2.0") }
        try validate(URL(fileURLWithPath: success.destination), "1.2.0")
        try validate(URL(fileURLWithPath: success.backup), "1.1.0"); checks += 1
        let rollback = try fixture("rollback")
        rejects("Launch failure") { try AppInstaller.replace(rollback, validate: validate) { _ in throw UpdateFailure("Simulated launch failure") } }
        try validate(URL(fileURLWithPath: rollback.destination), "1.1.0"); checks += 1
        let invalid = try fixture("invalid")
        rejects("Invalid stage") { try AppInstaller.replace(invalid, validate: { url, version in if version == "1.2.0" { throw UpdateFailure("Invalid bundle") }; try validate(url, version) }, launch: { _ in fatalError("Must not launch") }) }
        try validate(URL(fileURLWithPath: invalid.destination), "1.1.0"); checks += 1
        let linked = try fixture("symlink")
        try fm.removeItem(atPath: linked.staged)
        try fm.createSymbolicLink(atPath: linked.staged, withDestinationPath: linked.destination)
        rejects("Staged symlink") { try AppInstaller.validatePaths(linked) }
        expect(try Data(contentsOf: notebook) == notebookBytes, "Notebook unchanged")
        rejects("Invalid process") { try AppInstaller.waitForExit(1) }

        // Verify the actual distributable, including extraction and its universal signed bundle.
        let release = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("release")
        let actual = try UpdateSecurity.manifest(Data(contentsOf: release.appendingPathComponent(UpdateSecurity.manifestName)), signature: Data(contentsOf: release.appendingPathComponent(UpdateSecurity.signatureName)))
        let zip = release.appendingPathComponent(UpdateSecurity.archiveName)
        try UpdateSecurity.verifyArchive(zip, manifest: actual)
        try UpdateSecurity.validateArchivePaths(String(decoding: UpdateProcess.run("/usr/bin/unzip", ["-Z1", zip.path]), as: UTF8.self))
        let extracted = root.appendingPathComponent("extracted")
        _ = try UpdateProcess.run("/usr/bin/ditto", ["-x", "-k", zip.path, extracted.path])
        try UpdateSecurity.validateBundle(extracted.appendingPathComponent("Daybook.app"), version: actual.version); checks += 1
        print("Passed \(checks) updater checks, including signed release verification and rollback.")
    }
}
