import AppKit
import WebKit
import Security

// The service invokes this mode over stdin; secrets never become command-line arguments.
func handleKeychain() {
if CommandLine.arguments.contains("--keychain") {
    let keys: Set<String> = ["CANVAS_TOKEN", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "GMAIL_ACCESS_TOKEN", "GOOGLE_ACCOUNTS"]
    do {
        let input = FileHandle.standardInput.readDataToEndOfFile()
        guard let object = try JSONSerialization.jsonObject(with: input) as? [String: String],
              let key = object["key"], keys.contains(key), let action = object["action"] else { exit(2) }
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.avisharma.meridian", kSecAttrAccount as String: key]
        var status: OSStatus = errSecSuccess
        var value = ""
        if action == "get" {
            var find = query; find[kSecReturnData as String] = true; find[kSecMatchLimit as String] = kSecMatchLimitOne
            var result: CFTypeRef?
            status = SecItemCopyMatching(find as CFDictionary, &result)
            if let data = result as? Data { value = String(data: data, encoding: .utf8) ?? "" }
        } else if action == "set", let secret = object["value"] {
            let data = Data(secret.utf8)
            status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
            if status == errSecItemNotFound {
                var add = query; add[kSecValueData as String] = data
                add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
                status = SecItemAdd(add as CFDictionary, nil)
            }
        } else if action == "delete" { status = SecItemDelete(query as CFDictionary) }
        else { exit(2) }
        guard status == errSecSuccess || status == errSecItemNotFound else { exit(3) }
        FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: ["value": value]))
        exit(0)
    } catch { exit(2) }
}

}

@MainActor
final class DaybookDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var service: Process?
    var logHandle: FileHandle?
    var startupTimer: Timer?
    var attempts = 0
    let base = URL(string: "http://127.0.0.1:18765")!
    var support: URL!
    let desktop = DesktopCompanion()
    let updater = DaybookUpdater()
    var workspaceOpened = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Meridian", isDirectory: true)
            try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let config = WKWebViewConfiguration()
            web = WKWebView(frame: .zero, configuration: config)
            web.navigationDelegate = self; web.uiDelegate = self
            window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 880), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            window.title = "Daybook"; window.isReleasedWhenClosed = false
            window.minSize = NSSize(width: 760, height: 540); window.contentView = web
            window.setFrameAutosaveName("DaybookMainWindow"); window.center(); updater.window = window; setupMenu()
            web.loadHTMLString("<html><body style='background:#f8f9f6;font:18px -apple-system;color:#285b4a;padding:60px'><h1 style='font:36px Georgia'>A little more clarity.</h1><p>Opening your Daybook workspace…</p></body></html>", baseURL: nil)
            window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
            probeExisting()
        } catch { fail("Could not open the local workspace. " + error.localizedDescription) }
    }

    func probeExisting() {
        var request = URLRequest(url: base.appendingPathComponent("api/health")); request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { [weak self] data, _, _ in
            DispatchQueue.main.async {
                guard let self else { return }
                if let data, let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any], object["app"] as? String == "meridian", object["desktop"] as? Bool == true {
                    self.openWorkspace()
                } else { self.startService() }
            }
        }.resume()
    }

    func startService() {
        guard let resources = Bundle.main.resourceURL, let executable = Bundle.main.executableURL else { fail("The app bundle is incomplete."); return }
        let process = Process()
        process.executableURL = resources.appendingPathComponent("runtime/bin/python3")
        process.arguments = ["-m", "uvicorn", "meridian.app:app", "--host", "127.0.0.1", "--port", "18765", "--no-access-log"]
        process.currentDirectoryURL = support
        var env = ProcessInfo.processInfo.environment
        env["MERIDIAN_DB"] = support.appendingPathComponent("meridian.db").path
        env["MERIDIAN_SETTINGS_DIR"] = support.path
        env["MERIDIAN_KEYCHAIN_HELPER"] = executable.path
        env["MERIDIAN_DESKTOP"] = "1"; env["PYTHONUNBUFFERED"] = "1"
        env["MERIDIAN_TIMEZONE"] = TimeZone.current.identifier
        process.environment = env
        let log = support.appendingPathComponent("service.log")
        if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil, attributes: [.posixPermissions: 0o600]) }
        logHandle = try? FileHandle(forWritingTo: log); _ = try? logHandle?.seekToEnd()
        process.standardOutput = logHandle; process.standardError = logHandle
        do { try process.run(); service = process }
        catch { fail("The local runtime could not start. " + error.localizedDescription); return }
        startupTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in Task { @MainActor in self?.poll() } }
    }

    func poll() {
        attempts += 1
        if attempts > 480 || (service != nil && service?.isRunning == false) {
            startupTimer?.invalidate()
            let alert = NSAlert(); alert.messageText = "Daybook is taking longer to open"
            alert.informativeText = "Unlock your login keychain if needed, then try again. Your notebook is preserved. Details are in the service log in Application Support."
            alert.addButton(withTitle: "Try Again"); alert.addButton(withTitle: "Quit")
            if alert.runModal() == .alertFirstButtonReturn {
                attempts = 0
                if service?.isRunning == true {
                    startupTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in Task { @MainActor in self?.poll() } }
                } else { probeExisting() }
            } else { NSApp.terminate(nil) }
            return
        }
        var request = URLRequest(url: base.appendingPathComponent("api/health")); request.timeoutInterval = 0.5
        URLSession.shared.dataTask(with: request) { [weak self] data, _, _ in
            guard let data, let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any], object["app"] as? String == "meridian", object["desktop"] as? Bool == true else { return }
            DispatchQueue.main.async { self?.startupTimer?.invalidate(); self?.openWorkspace() }
        }.resume()
    }

    func openWorkspace() {
        guard !workspaceOpened else { return }; workspaceOpened = true
        navigate("today")
        desktop.openTask = { [weak self] id in self?.navigate("tasks", task: id) }
        desktop.start(folder: support)
        updater.start()
    }
    func navigate(_ view: String, task: String? = nil) {
        var parts = URLComponents(url: base, resolvingAgainstBaseURL: false)!
        parts.fragment = view
        if let task { parts.queryItems = [URLQueryItem(name: "task", value: task)] }
        web.load(URLRequest(url: parts.url!)); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    func fail(_ message: String) {
        let alert = NSAlert(); alert.messageText = "Daybook couldn’t open"; alert.informativeText = message
        alert.runModal()
    }
    @objc func reloadWorkspace() { web.reload() }
    @objc func showConnections() { navigate("sources") }
    @objc func toggleDesktop() { desktop.toggle() }
    @objc func openDataFolder() { NSWorkspace.shared.open(support) }
    func setupMenu() {
        let bar = NSMenu(); let appItem = NSMenuItem(); bar.addItem(appItem)
        let appMenu = NSMenu(); appItem.submenu = appMenu
        appMenu.addItem(withTitle: "About Daybook", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        updater.addMenu(to: appMenu)
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide Daybook", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "Quit Daybook", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let workspace = NSMenuItem(); bar.addItem(workspace); let menu = NSMenu(title: "Workspace"); workspace.submenu = menu
        for (title, action, key) in [("Connections", #selector(showConnections), ","), ("Reload", #selector(reloadWorkspace), "r"), ("Show Data Folder", #selector(openDataFolder), ""), ("Floating Tasks", #selector(toggleDesktop), "T")] {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: key); item.target = self; if title == "Floating Tasks" { item.keyEquivalentModifierMask = [.command, .shift] }; menu.addItem(item)
        }
        let edit = NSMenuItem(); bar.addItem(edit); let edits = NSMenu(title: "Edit"); edit.submenu = edits
        for (title, selector, key) in [("Undo","undo:","z"),("Cut","cut:","x"),("Copy","copy:","c"),("Paste","paste:","v"),("Select All","selectAll:","a")] { edits.addItem(withTitle: title, action: NSSelectorFromString(selector), keyEquivalent: key) }
        NSApp.mainMenu = bar
    }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { decisionHandler(.cancel); return }
        if url.scheme == "http", url.host == "127.0.0.1", url.port == 18765 {
            if url.path == "/api/calendar.ics" || url.path == "/api/backup" { saveDownload(url); decisionHandler(.cancel) }
            else { decisionHandler(.allow) }
        } else {
            if url.scheme == "https" { NSWorkspace.shared.open(url) }
            decisionHandler(.cancel)
        }
    }
    func saveDownload(_ url: URL) {
        URLSession.shared.dataTask(with: url) { [weak self] data, response, error in
            guard let data, error == nil, let response = response as? HTTPURLResponse, response.statusCode == 200 else { return }
            DispatchQueue.main.async {
                let panel = NSSavePanel(); panel.nameFieldStringValue = url.path == "/api/backup" ? "Daybook-notebook.json" : "Daybook-calendar.ics"
                guard let window = self?.window else { return }
                panel.beginSheetModal(for: window) { result in
                    guard result == .OK, let destination = panel.url else { return }
                    do { try data.write(to: destination, options: .atomic); try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path) }
                    catch { self?.fail("Could not save the export. " + error.localizedDescription) }
                }
            }
        }.resume()
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, url.scheme == "https" { NSWorkspace.shared.open(url) }; return nil
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { window.makeKeyAndOrderFront(nil); return true }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationWillTerminate(_ notification: Notification) { startupTimer?.invalidate(); desktop.stop(); if service?.isRunning == true { service?.terminate() }; try? logHandle?.close() }
}

@main
struct DaybookMain {
    @MainActor static func main() {
        handleKeychain()
        let application = NSApplication.shared
        let delegate = DaybookDelegate()
        application.delegate = delegate
        application.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { application.run() }
    }
}
