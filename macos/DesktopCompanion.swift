import AppKit
import UserNotifications

private final class DesktopTaskStack: NSStackView {
    override var isFlipped: Bool { true }
}

final class DesktopCompanion: NSObject, NSWindowDelegate, UNUserNotificationCenterDelegate {
    private var preferences = DesktopPreferences()
    private var preferenceURL: URL!
    private var panel: NSPanel!
    private var stack: NSStackView!
    private var tasks: [DesktopTask] = []
    private var settings: NSPanel?
    private var countField: NSTextField!
    private var unitPicker: NSPopUpButton!
    private var enabled: NSButton!
    private var status: NSTextField!
    private var timer: Timer?
    var openTask: ((String?) -> Void)?

    func start(folder: URL) {
        preferenceURL = folder.appendingPathComponent("desktop-preferences.json")
        if let data = try? Data(contentsOf: preferenceURL), let saved = try? JSONDecoder().decode(DesktopPreferences.self, from: data) {
            preferences = saved
        }
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 340, height: 440), styleMask: [.titled, .closable, .resizable, .utilityWindow], backing: .buffered, defer: false)
        panel.title = "Daybook · Tasks"
        panel.minSize = NSSize(width: 280, height: 260)
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isReleasedWhenClosed = false
        panel.delegate = self
        panel.setFrameAutosaveName("DaybookDesktopTasks")
        panel.center()
        let scroll = NSScrollView(frame: panel.contentView!.bounds)
        scroll.autoresizingMask = [.width, .height]
        scroll.hasVerticalScroller = true
        stack = DesktopTaskStack()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top: 16, left: 16, bottom: 16, right: 16)
        stack.translatesAutoresizingMaskIntoConstraints = false
        scroll.documentView = stack
        panel.contentView!.addSubview(scroll)
        NSLayoutConstraint.activate([stack.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor)])
        UNUserNotificationCenter.current().delegate = self
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in self?.reload(folder: folder) }
        reload(folder: folder)
        scheduleReminder()
        if preferences.visible { panel.orderFront(nil) }
    }

    func reload(folder: URL) {
        guard let data = try? Data(contentsOf: folder.appendingPathComponent("notebook.json")) else { return }
        update(data)
    }

    func update(_ data: Data) {
        let formatter = DateFormatter(); formatter.dateFormat = "yyyy-MM-dd"; formatter.locale = Locale(identifier: "en_US_POSIX")
        let today = formatter.string(from: Date())
        guard let pending = try? DesktopTask.pending(in: data, today: today) else { return }
        tasks = pending
        stack.arrangedSubviews.forEach { stack.removeArrangedSubview($0); $0.removeFromSuperview() }
        let heading = NSTextField(labelWithString: "\(tasks.count) open \(tasks.count == 1 ? "task" : "tasks")")
        heading.font = .boldSystemFont(ofSize: 16)
        stack.addArrangedSubview(heading)
        if tasks.isEmpty {
            let empty = NSTextField(wrappingLabelWithString: "A little breathing room. Add a task in My day when you’re ready.")
            stack.addArrangedSubview(empty)
        }
        for task in tasks {
            let button = NSButton(title: task.title, target: self, action: #selector(selectTask(_:)))
            button.identifier = NSUserInterfaceItemIdentifier(task.id)
            button.bezelStyle = .inline
            button.alignment = .left
            button.cell?.wraps = true
            button.cell?.isScrollable = false
            button.setAccessibilityLabel("Open task: " + task.title)
            stack.addArrangedSubview(button)
            button.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -32).isActive = true
            if !task.due.isEmpty {
                let text = task.due == today ? "Due today" : task.due < today ? "Overdue · \(task.due)" : "Due \(task.due)"
                let label = NSTextField(labelWithString: text)
                label.font = .systemFont(ofSize: 12)
                label.textColor = task.due < today ? .systemRed : .secondaryLabelColor
                stack.addArrangedSubview(label)
            }
        }
        stack.addArrangedSubview(NSButton(title: "Open My day", target: self, action: #selector(openNotebook)))
        stack.addArrangedSubview(NSButton(title: "Reminder settings…", target: self, action: #selector(showSettings)))
    }

    @objc private func selectTask(_ sender: NSButton) { openTask?(sender.identifier?.rawValue) }
    @objc private func openNotebook() { openTask?(nil) }
    @objc func toggle() {
        preferences.visible.toggle()
        if preferences.visible { panel.makeKeyAndOrderFront(nil) } else { panel.orderOut(nil) }
        savePreferences()
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if sender === panel { preferences.visible = false; savePreferences() }
        return true
    }

    private func savePreferences() {
        do { try JSONEncoder().encode(preferences).write(to: preferenceURL, options: .atomic) }
        catch {
            let alert = NSAlert(); alert.messageText = "Couldn’t save desktop settings"; alert.informativeText = error.localizedDescription; alert.runModal()
        }
    }

    @objc func showSettings() {
        if let settings { settings.makeKeyAndOrderFront(nil); return }
        let window = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 400, height: 330), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Daybook Reminders"; window.isReleasedWhenClosed = false; window.center()
        let content = NSStackView(); content.orientation = .vertical; content.alignment = .leading; content.spacing = 16
        content.edgeInsets = NSEdgeInsets(top: 20, left: 20, bottom: 20, right: 20)
        content.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(content)
        NSLayoutConstraint.activate([content.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor), content.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor), content.topAnchor.constraint(equalTo: window.contentView!.topAnchor)])
        enabled = NSButton(checkboxWithTitle: "Remind me to check my open tasks", target: nil, action: nil)
        enabled.state = preferences.reminders ? .on : .off
        content.addArrangedSubview(enabled)
        countField = NSTextField(string: String(preferences.count)); countField.widthAnchor.constraint(equalToConstant: 56).isActive = true
        countField.setAccessibilityLabel("Reminder interval, 1 to 168")
        unitPicker = NSPopUpButton(); unitPicker.addItems(withTitles: ["hours", "days", "weeks"]); unitPicker.selectItem(withTitle: preferences.unit)
        unitPicker.setAccessibilityLabel("Reminder interval unit")
        let row = NSStackView(views: [NSTextField(labelWithString: "Every"), countField, unitPicker]); row.spacing = 8
        content.addArrangedSubview(row)
        content.addArrangedSubview(NSTextField(wrappingLabelWithString: "Choose 1–168 hours, days, or weeks. Reminders start from Save. Daybook must be running; reminders pause when you quit and resume at launch."))
        status = NSTextField(wrappingLabelWithString: "Notifications are optional. macOS will ask for permission when you enable them.")
        status.setAccessibilityRole(.staticText)
        content.addArrangedSubview(status)
        content.addArrangedSubview(NSButton(title: "Save", target: self, action: #selector(applySettings)))
        settings = window; window.makeKeyAndOrderFront(nil)
    }

    @objc private func applySettings() {
        guard let number = Int(countField.stringValue), (1...168).contains(number) else { status.stringValue = "Enter a whole number from 1 to 168."; return }
        let wantsReminders = enabled.state == .on
        let unit = unitPicker.titleOfSelectedItem ?? "days"
        if wantsReminders {
            UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { [weak self] granted, error in
                DispatchQueue.main.async {
                    guard let self else { return }
                    guard granted else { self.status.stringValue = error?.localizedDescription ?? "Allow Daybook notifications in System Settings, then try again."; return }
                    self.commitSettings(count: number, unit: unit, reminders: true)
                }
            }
        } else { commitSettings(count: number, unit: unit, reminders: false) }
    }

    private func commitSettings(count: Int, unit: String, reminders: Bool) {
        preferences.count = count; preferences.unit = unit; preferences.reminders = reminders
        savePreferences()
        scheduleReminder()
        settings?.orderOut(nil)
    }

    // A timer checks the current notebook at delivery time, avoiding stale task
    // notifications after completion. No requests are left behind on app quit.
    private var reminderTimer: Timer?
    func scheduleReminder() {
        reminderTimer?.invalidate(); reminderTimer = nil
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ["daybook-open-tasks"])
        guard preferences.reminders, let interval = preferences.interval else { return }
        reminderTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            guard let self, !self.tasks.isEmpty else { return }
            let content = UNMutableNotificationContent()
            content.title = "A moment for your tasks"
            content.body = "\(self.tasks.count) open \(self.tasks.count == 1 ? "task" : "tasks") in Daybook. Open My day to choose your next step."
            content.sound = .default
            let request = UNNotificationRequest(identifier: "daybook-open-tasks", content: content, trigger: nil)
            UNUserNotificationCenter.current().add(request) { error in
                if let error { NSLog("Daybook reminder failed: %@", error.localizedDescription) }
            }
        }
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) { completionHandler([.banner, .sound]) }
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        DispatchQueue.main.async { [weak self] in self?.openTask?(nil) }
        completionHandler()
    }
}
