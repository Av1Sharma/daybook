import Foundation
import Darwin

struct InstallJob: Codable {
    let destination: String
    let staged: String
    let backup: String
    let parentPID: Int32
    let previousVersion: String
    let version: String
    let resultFile: String
    let dataDirectory: String?
}
enum AppInstaller {
    static func validatePaths(_ job: InstallJob) throws {
        let fm = FileManager.default
        let destination = URL(fileURLWithPath:job.destination).standardizedFileURL
        let stage = URL(fileURLWithPath:job.staged).standardizedFileURL
        let backup = URL(fileURLWithPath:job.backup).standardizedFileURL
        let parent = destination.deletingLastPathComponent()
        guard destination.pathExtension == "app", !destination.path.hasPrefix("/Volumes/"), !destination.path.contains("/AppTranslocation/"),
              parent == stage.deletingLastPathComponent(), parent == backup.deletingLastPathComponent(),
              stage.lastPathComponent.hasPrefix(".Daybook.update-"), backup.lastPathComponent.hasPrefix(".Daybook.previous-"),
              destination != stage, destination != backup, stage != backup,
              parent.resolvingSymlinksInPath().path == parent.path,
              fm.isWritableFile(atPath:parent.path), !fm.fileExists(atPath:backup.path) else {
            throw UpdateFailure("Daybook can’t replace the app in this location. Move it to a writable Applications folder, reopen it, and try again.")
        }
        for url in [destination,stage] {
            if try url.resourceValues(forKeys:[.isSymbolicLinkKey]).isSymbolicLink == true {throw UpdateFailure("The app location must not be a symbolic link.")}
        }
        guard try AppVersion(job.version) > AppVersion(job.previousVersion) else {throw UpdateFailure("Older or identical versions cannot replace the installed app.")}
    }
    static func replace(_ job: InstallJob, validate: (URL,String) throws -> Void = UpdateSecurity.validateBundle, launch: (URL) throws -> Void) throws {
        try validatePaths(job)
        let fm=FileManager.default
        let destination=URL(fileURLWithPath:job.destination),stage=URL(fileURLWithPath:job.staged),backup=URL(fileURLWithPath:job.backup)
        try validate(destination,job.previousVersion)
        try validate(stage,job.version)
        try fm.moveItem(at:destination,to:backup)
        do {
            try fm.moveItem(at:stage,to:destination)
            try validate(destination,job.version)
            try launch(destination)
        } catch {
            do {
                if fm.fileExists(atPath:destination.path) {try fm.removeItem(at:destination)}
                try fm.moveItem(at:backup,to:destination)
            } catch {
                throw UpdateFailure("The update could not finish. Your previous app is preserved at \(backup.path). Your notebook data has not been changed.")
            }
            throw UpdateFailure("The update could not finish, so the previous app was restored. Your notebook data has not been changed.")
        }
    }
    static func waitForExit(_ pid: Int32, timeout: TimeInterval = 45) throws {
        guard pid > 1, pid != getpid() else {throw UpdateFailure("The updater received an invalid application process.")}
        let deadline=Date().addingTimeInterval(timeout)
        while kill(pid,0)==0 {
            guard Date()<deadline else {throw UpdateFailure("Daybook did not quit in time. The installed app was not replaced.")}
            Thread.sleep(forTimeInterval:0.2)
        }
    }
}
