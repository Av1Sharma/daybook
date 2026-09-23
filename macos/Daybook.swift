import AppKit
import WebKit
import UniformTypeIdentifiers

final class AppDelegate: NSObject, NSApplicationDelegate, WKScriptMessageHandlerWithReply, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var notebook: URL!
    var loadFailed = false
    var pendingSaves = 0
    var terminateAfterSave = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let override = ProcessInfo.processInfo.environment["DAYBOOK_DATA_DIRECTORY"]
            let folder = override.map { URL(fileURLWithPath: $0) } ?? FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0].appendingPathComponent("Daybook",isDirectory:true)
            try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
            notebook = folder.appendingPathComponent("notebook.json")
            var initial: Any = NSNull()
            if FileManager.default.fileExists(atPath:notebook.path) {
                let data = try Data(contentsOf:notebook)
                try validate(data)
                initial = String(decoding:data,as:UTF8.self)
            }
            let object: [String:Any] = ["initial":initial]
            let encoded = try JSONSerialization.data(withJSONObject:object).base64EncodedString()
            let setup = "window.daybookNative = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob('\(encoded)'), c => c.charCodeAt(0))));"
            let config = WKWebViewConfiguration()
            config.websiteDataStore = .nonPersistent()
            config.userContentController.addScriptMessageHandler(self,contentWorld:.page,name:"notebook")
            config.userContentController.addUserScript(WKUserScript(source:setup,injectionTime:.atDocumentStart,forMainFrameOnly:true))
            web = WKWebView(frame:.zero,configuration:config)
            web.navigationDelegate = self
            window = NSWindow(contentRect:NSRect(x:0,y:0,width:1280,height:850),styleMask:[.titled,.closable,.miniaturizable,.resizable],backing:.buffered,defer:false)
            window.title = "Daybook"
            window.minSize = NSSize(width:680,height:500)
            window.contentView = web
            window.setFrameAutosaveName("DaybookMainWindow")
            window.center()
            configureMenu()
            guard let page = Bundle.main.url(forResource:"index",withExtension:"html") else { throw NSError(domain:"Daybook",code:1,userInfo:[NSLocalizedDescriptionKey:"The bundled notebook page is missing."]) }
            web.loadFileURL(page,allowingReadAccessTo:page.deletingLastPathComponent())
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps:true)
        } catch {
            loadFailed = true
            let alert=NSAlert(); alert.messageText="Daybook couldn’t open your notebook"; alert.informativeText="Your existing data has not been replaced.\n\n"+error.localizedDescription;alert.runModal(); NSApp.terminate(nil)
        }
    }

    func validate(_ data: Data) throws {
        guard let object=try JSONSerialization.jsonObject(with:data) as? [String:Any],object["version"] as? Int == 1,let tasks=object["tasks"] as? [[String:Any]], tasks.allSatisfy({ $0["id"] is String && $0["title"] is String && $0["createdAt"] is String }) else { throw NSError(domain:"Daybook",code:2,userInfo:[NSLocalizedDescriptionKey:"The notebook file is not a supported Daybook backup."]) }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage, replyHandler: @escaping (Any?, String?) -> Void) {
        guard message.frameInfo.isMainFrame, message.frameInfo.request.url?.isFileURL == true,let body=message.body as? [String:Any],let action=body["action"] as? String,let raw=body["json"] as? String,let data=raw.data(using:.utf8) else {replyHandler(nil,"Invalid notebook request");return}
        do {try validate(data)} catch {replyHandler(nil,error.localizedDescription);return}
        if action == "save" {
            if loadFailed { replyHandler(nil,"The existing notebook could not be loaded.");return }
            pendingSaves += 1
            do {
                // Atomic replacement prevents a partial notebook when an app or machine stops mid-write.
                try data.write(to:notebook,options:.atomic)
                replyHandler(["saved":true],nil)
            } catch {replyHandler(nil,error.localizedDescription)}
            pendingSaves -= 1
            if terminateAfterSave && pendingSaves == 0 { NSApp.reply(toApplicationShouldTerminate:true) }
        } else if action == "export" {
            do {
                let folder=notebook.deletingLastPathComponent().appendingPathComponent("Backups",isDirectory:true)
                try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
                let stamp=ISO8601DateFormatter().string(from:Date()).replacingOccurrences(of:":",with:"-")
                let destination=folder.appendingPathComponent("Daybook-"+stamp+"-"+String(UUID().uuidString.prefix(6))+".json")
                try data.write(to:destination,options:.atomic)
                replyHandler(["saved":true,"path":destination.path],nil)
                NSWorkspace.shared.activateFileViewerSelecting([destination])
            } catch {replyHandler(nil,error.localizedDescription)}
        } else {replyHandler(nil,"Unknown notebook action")}
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url=action.request.url else {decisionHandler(.cancel);return}
        // The app is offline. Do not let external pages gain access to the storage bridge.
        decisionHandler(url.isFileURL ? .allow : .cancel)
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if pendingSaves > 0 {terminateAfterSave=true;return .terminateLater};return .terminateNow
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool {true}
    func configureMenu() {
        let bar=NSMenu()
        let appItem=NSMenuItem();bar.addItem(appItem)
        let appMenu=NSMenu();appItem.submenu=appMenu
        appMenu.addItem(withTitle:"About Daybook",action:#selector(NSApplication.orderFrontStandardAboutPanel(_:)),keyEquivalent:"")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle:"Hide Daybook",action:#selector(NSApplication.hide(_:)),keyEquivalent:"h")
        appMenu.addItem(withTitle:"Quit Daybook",action:#selector(NSApplication.terminate(_:)),keyEquivalent:"q")
        let edit=NSMenuItem();bar.addItem(edit);let menu=NSMenu(title:"Edit");edit.submenu=menu
        for (title,selector,key) in [("Undo","undo:","z"),("Cut","cut:","x"),("Copy","copy:","c"),("Paste","paste:","v"),("Select All","selectAll:","a")] {menu.addItem(withTitle:title,action:NSSelectorFromString(selector),keyEquivalent:key)}
        NSApp.mainMenu=bar
    }
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate=delegate
app.setActivationPolicy(.regular)
app.run()
