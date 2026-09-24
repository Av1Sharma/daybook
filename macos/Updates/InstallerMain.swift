import Foundation

@main
struct InstallerMain {
    static func main() {
        guard CommandLine.arguments.count==2 else {exit(1)}
        let file=URL(fileURLWithPath:CommandLine.arguments[1])
        guard let bytes=try? Data(contentsOf:file),let job=try? JSONDecoder().decode(InstallJob.self,from:bytes) else {exit(1)}
        func report(_ message:String) {
            let record:[String:Any]=["message":message,"version":job.version]
            if let data=try? JSONSerialization.data(withJSONObject:record){try? data.write(to:URL(fileURLWithPath:job.resultFile),options:.atomic)}
        }
        func launch(_ app:URL) throws {
            var args=["-n",app.path,"--env","DAYBOOK_UPDATE_RESULT="+job.resultFile]
            if let directory=job.dataDirectory {args += ["--env","DAYBOOK_DATA_DIRECTORY="+directory]}
            _ = try UpdateProcess.run("/usr/bin/open",args,timeout:30)
        }
        do {
            try AppInstaller.waitForExit(job.parentPID)
            report("Daybook was updated to "+job.version+". Your notebook is unchanged.")
            try AppInstaller.replace(job,launch:launch)
        } catch {
            report(error.localizedDescription)
            // Relaunch the old app only after the original process has exited and a valid old bundle remains.
            if kill(job.parentPID,0) != 0,
               (try? UpdateSecurity.validateBundle(URL(fileURLWithPath:job.destination),version:job.previousVersion)) != nil {
                try? launch(URL(fileURLWithPath:job.destination))
            }
            exit(1)
        }
    }
}
