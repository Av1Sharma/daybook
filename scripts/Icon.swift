import AppKit
let folder = URL(fileURLWithPath: CommandLine.arguments[1])
try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
for size in [16,32,128,256,512] {
    for scale in [1,2] {
        let pixels = size * scale
        let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        let p = CGFloat(pixels)
        NSColor(calibratedRed: 36/255, green: 89/255, blue: 79/255, alpha: 1).setFill()
        NSBezierPath(roundedRect: NSRect(x: p*0.06, y: p*0.06, width: p*0.88, height: p*0.88), xRadius: p*0.23, yRadius: p*0.23).fill()
        NSColor(calibratedRed: 244/255, green: 248/255, blue: 241/255, alpha: 1).setStroke()
        let ring = NSBezierPath(ovalIn: NSRect(x: p*0.239, y: p*0.239, width: p*0.522, height: p*0.522))
        ring.lineWidth = p*0.041; ring.stroke()
        let lines = NSBezierPath(); lines.lineWidth = p*0.041; lines.lineCapStyle = .round
        lines.move(to: NSPoint(x: p*0.5, y: p*0.239))
        lines.curve(to: NSPoint(x: p*0.5, y: p*0.761), controlPoint1: NSPoint(x: p*0.28, y: p*0.40), controlPoint2: NSPoint(x: p*0.28, y: p*0.60))
        lines.move(to: NSPoint(x: p*0.5, y: p*0.239))
        lines.curve(to: NSPoint(x: p*0.5, y: p*0.761), controlPoint1: NSPoint(x: p*0.72, y: p*0.40), controlPoint2: NSPoint(x: p*0.72, y: p*0.60))
        lines.move(to: NSPoint(x: p*0.239, y: p*0.5)); lines.line(to: NSPoint(x: p*0.761, y: p*0.5)); lines.stroke()
        NSGraphicsContext.restoreGraphicsState()
        let suffix = scale == 2 ? "@2x" : ""
        try rep.representation(using: .png, properties: [:])!.write(to: folder.appendingPathComponent("icon_\(size)x\(size)\(suffix).png"))
    }
}
