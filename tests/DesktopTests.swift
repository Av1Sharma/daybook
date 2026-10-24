import Foundation

@main
struct DesktopTests {
    static func main() throws {
        let rows: [[String: Any]] = [
            ["id": "later", "title": "Later", "due": "2026-11-01"],
            ["id": "now", "title": "Now", "due": "2026-10-23", "completedAt": NSNull(), "deletedAt": NSNull()],
            ["id": "old", "title": "Overdue", "due": "2026-10-01"],
            ["id": "none", "title": "No due date"],
            ["id": "done", "title": "Done", "completedAt": "2026-10-22"],
            ["id": "deleted", "title": "Deleted", "deletedAt": "2026-10-22"],
            ["id": "reference", "title": "Reference", "recordType": "reference"],
            ["id": "internship", "title": "Internship check-in", "surface": "internships"],
            ["id": "future", "title": "Future repeat", "available": "2026-10-24"],
            ["title": "Missing ID"]
        ]
        let data = try JSONSerialization.data(withJSONObject: ["version": 1, "tasks": rows])
        let tasks = try DesktopTask.pending(in: data, today: "2026-10-23")
        precondition(tasks.map(\.id) == ["old", "now", "later", "none"], "Show actionable tasks in deadline order")
        let empty = try DesktopTask.pending(in: JSONSerialization.data(withJSONObject: ["tasks": []]), today: "2026-10-23")
        precondition(empty.isEmpty)
        var preferences = DesktopPreferences()
        precondition(!preferences.reminders && !preferences.visible)
        for (unit, seconds) in [("hours", 3600.0), ("days", 86400.0), ("weeks", 604800.0)] {
            preferences.unit = unit; preferences.count = 3
            precondition(preferences.interval == seconds * 3)
        }
        preferences.count = 0; precondition(preferences.interval == nil)
        preferences.count = 169; precondition(preferences.interval == nil)
        preferences.count = 1; preferences.unit = "invalid"; precondition(preferences.interval == nil)
        let roundtrip = try JSONDecoder().decode(DesktopPreferences.self, from: JSONEncoder().encode(preferences))
        precondition(roundtrip.count == preferences.count && roundtrip.unit == preferences.unit)
        print("Desktop task filtering, ordering, empty state, reminder intervals, and preferences passed")
    }
}
