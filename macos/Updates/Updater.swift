import AppKit

@MainActor
final class DaybookUpdater: NSObject {
    weak var window: NSWindow?
    var beforeInstall: (() -> Void)?
    var installFailed: (() -> Void)?
    private var timer: Timer?
    private var checking=false
    private var installing=false
    private var candidate: UpdateCandidate?
    private let defaults=UserDefaults.standard
    private let current=Bundle.main.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String ?? "0.0.0"
    private var checkItem: NSMenuItem!
    private var automaticItem: NSMenuItem!
    private let autoKey="daybook.automaticallyCheckForUpdates"
    private var automatic: Bool {defaults.object(forKey:autoKey)==nil || defaults.bool(forKey:autoKey)}

    func addMenu(to menu:NSMenu) {
        checkItem=menu.addItem(withTitle:"Check for Updates…",action:#selector(manualCheck),keyEquivalent:"")
        checkItem.target=self
        automaticItem=menu.addItem(withTitle:"Automatically Check for Updates",action:#selector(toggleAutomatic),keyEquivalent:"")
        automaticItem.target=self;automaticItem.state=automatic ? .on : .off
    }
    func start() {
        if let path=ProcessInfo.processInfo.environment["DAYBOOK_UPDATE_RESULT"],
           let bytes=try? Data(contentsOf:URL(fileURLWithPath:path)),
           let record=try? JSONSerialization.jsonObject(with:bytes) as? [String:Any],let message=record["message"] as? String {
            DispatchQueue.main.async {self.alert("Daybook update",message)}
        }
        // Test copies can disable background networking without changing the app's ordinary default.
        guard ProcessInfo.processInfo.environment["DAYBOOK_DISABLE_AUTO_CHECK"] != "1" else {return}
        DispatchQueue.main.asyncAfter(deadline:.now()+8) { [weak self] in if self?.automatic == true {self?.check(manual:false)} }
        timer=Timer.scheduledTimer(withTimeInterval:6*60*60,repeats:true){[weak self] _ in
            Task {@MainActor in if self?.automatic == true {self?.check(manual:false)}}
        }
    }
    @objc func toggleAutomatic(){defaults.set(!automatic,forKey:autoKey);automaticItem.state=automatic ? .on : .off}
    @objc func manualCheck(){check(manual:true)}
    private func check(manual:Bool) {
        guard !checking && !installing else {return}
        if let candidate { offer(candidate,manual:manual);return }
        checking=true;checkItem.title="Checking for Updates…"
        let version=current
        Task {
            do {
                let found=try await Task.detached(priority:.utility){try GitHubUpdates.latest(current:version)}.value
                checking=false
                guard let found else {checkItem.title="Check for Updates…";if manual{alert("Daybook is up to date","You’re using Daybook "+version+". There are no newer releases.")};return}
                candidate=found;checkItem.title="Install Daybook "+found.manifest.version+"…"
                offer(found,manual:manual)
            } catch {
                checking=false;checkItem.title="Check for Updates…"
                if manual {alert("Couldn’t check for updates",error.localizedDescription)}
            }
        }
    }
    private func offer(_ update:UpdateCandidate,manual:Bool) {
        guard let window,window.attachedSheet==nil else {return}
        let key="daybook.deferUpdate."+update.manifest.version
        if !manual,let until=defaults.object(forKey:key) as? Date,until>Date(){return}
        let panel=NSAlert();panel.messageText="Daybook "+update.manifest.version+" is available"
        panel.informativeText="Install the signed update from your private GitHub repository and reopen Daybook. Your tasks, history, and reminders stay on this Mac."
        panel.addButton(withTitle:"Install & Relaunch");panel.addButton(withTitle:"Later")
        panel.beginSheetModal(for:window){[weak self] response in
            if response == .alertFirstButtonReturn {self?.install(update)}
            else {self?.defaults.set(Date().addingTimeInterval(24*60*60),forKey:key)}
        }
    }
    private func install(_ update:UpdateCandidate) {
        guard !installing else{return}
        let destination=Bundle.main.bundleURL.standardizedFileURL
        let parent=destination.deletingLastPathComponent()
        guard !destination.path.hasPrefix("/Volumes/"),!destination.path.contains("/AppTranslocation/"),FileManager.default.isWritableFile(atPath:parent.path) else {
            alert("Move Daybook before updating","Quit Daybook and move it from the disk image into Applications or a writable folder. Reopen that copy, then check for updates again.");return
        }
        installing=true;checkItem.title="Downloading update…";beforeInstall?()
        let progress=NSPanel(contentRect:NSRect(x:0,y:0,width:420,height:120),styleMask:[.titled],backing:.buffered,defer:false)
        progress.title="Updating Daybook"
        let label=NSTextField(labelWithString:"Downloading and verifying the signed update…")
        label.frame=NSRect(x:24,y:68,width:375,height:24)
        let indicator=NSProgressIndicator(frame:NSRect(x:24,y:30,width:370,height:16));indicator.style = .bar;indicator.isIndeterminate=true;indicator.startAnimation(nil)
        progress.contentView?.addSubview(label);progress.contentView?.addSubview(indicator)
        window?.beginSheet(progress)
        let oldVersion=current
        Task {
            do {
                let jobPath=try await Task.detached(priority:.utility) { () throws -> URL in
                    let prepared=try GitHubUpdates.prepare(update)
                    let id=UUID().uuidString
                    let staged=parent.appendingPathComponent(".Daybook.update-"+id+".app")
                    let backup=parent.appendingPathComponent(".Daybook.previous-"+id+".app")
                    let fm=FileManager.default
                    let job=InstallJob(destination:destination.path,staged:staged.path,backup:backup.path,parentPID:ProcessInfo.processInfo.processIdentifier,previousVersion:oldVersion,version:update.manifest.version,resultFile:update.folder.appendingPathComponent("result.json").path,dataDirectory:ProcessInfo.processInfo.environment["DAYBOOK_DATA_DIRECTORY"])
                    do {
                        try fm.copyItem(at:prepared,to:staged)
                        try AppInstaller.validatePaths(job)
                        try UpdateSecurity.validateBundle(staged,version:update.manifest.version)
                        let file=update.folder.appendingPathComponent("install-job.json")
                        try JSONEncoder().encode(job).write(to:file,options:.atomic)
                        let helper=update.folder.appendingPathComponent("DaybookInstaller")
                        try fm.copyItem(at:destination.appendingPathComponent("Contents/MacOS/DaybookInstaller"),to:helper)
                        return file
                    } catch {try? fm.removeItem(at:staged);throw error}
                }.value
                label.stringValue="Installing and reopening Daybook…"
                let helper=Process();helper.executableURL=jobPath.deletingLastPathComponent().appendingPathComponent("DaybookInstaller");helper.arguments=[jobPath.path]
                helper.standardOutput=FileHandle.nullDevice;helper.standardError=FileHandle.nullDevice;helper.standardInput=FileHandle.nullDevice
                try helper.run()
                window?.endSheet(progress)
                NSApp.terminate(nil)
            } catch {
                window?.endSheet(progress);installing=false;checkItem.title="Install Daybook "+update.manifest.version+"…";installFailed?()
                alert("Daybook wasn’t updated",error.localizedDescription+"\n\nYour installed app and notebook are unchanged.")
            }
        }
    }
    private func alert(_ title:String,_ message:String) {
        guard let window,window.attachedSheet==nil else{return}
        let panel=NSAlert();panel.messageText=title;panel.informativeText=message;panel.addButton(withTitle:"OK");panel.beginSheetModal(for:window)
    }
}
