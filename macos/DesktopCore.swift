import Foundation

struct DesktopTask {
    let id: String
    let title: String
    let due: String

    static func pending(in data: Data, today: String) throws -> [DesktopTask] {
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let rows = object?["tasks"] as? [[String: Any]] ?? []
        return rows.compactMap { row -> DesktopTask? in
            guard let id = row["id"] as? String, let title = row["title"] as? String,
                  row["completedAt"] == nil || row["completedAt"] is NSNull,
                  row["deletedAt"] == nil || row["deletedAt"] is NSNull,
                  row["recordType"] as? String != "reference",
                  row["surface"] as? String != "internships",
                  (row["available"] as? String ?? "") <= today else { return nil }
            return DesktopTask(id: id, title: title, due: row["due"] as? String ?? "")
        }.sorted {
            let a = $0.due.isEmpty ? "9999" : $0.due
            let b = $1.due.isEmpty ? "9999" : $1.due
            return a == b ? $0.title.localizedStandardCompare($1.title) == .orderedAscending : a < b
        }
    }
}

struct DesktopPreferences: Codable {
    var visible = false
    var reminders = false
    var count = 1
    var unit = "days"

    var interval: TimeInterval? {
        let seconds: [String: Double] = ["hours": 3600, "days": 86400, "weeks": 604800]
        guard (1...168).contains(count), let scale = seconds[unit] else { return nil }
        return Double(count) * scale
    }
}
