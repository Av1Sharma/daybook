import AppKit
let directory = URL(fileURLWithPath: CommandLine.arguments[1])
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
for size in [16,32,128,256,512] {
    for scale in [1,2] {
        let px = size * scale
        let rep = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:px,pixelsHigh:px,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep:rep)!
        NSColor(red: 0.13, green: 0.16, blue: 0.12, alpha: 1).setFill()
        NSBezierPath(roundedRect: NSRect(x: 0, y: 0, width: px, height: px), xRadius: CGFloat(px)*0.22, yRadius: CGFloat(px)*0.22).fill()
        let style = NSMutableParagraphStyle(); style.alignment = .center
        let attrs: [NSAttributedString.Key: Any] = [.font: NSFont(name:"Georgia-Bold",size:CGFloat(px)*0.7) ?? NSFont.boldSystemFont(ofSize:CGFloat(px)*0.7), .foregroundColor: NSColor(red:0.90,green:0.94,blue:0.67,alpha:1), .paragraphStyle:style]
        ("d." as NSString).draw(in:NSRect(x:0,y:CGFloat(px)*0.08,width:CGFloat(px),height:CGFloat(px)*0.88),withAttributes:attrs)
        NSGraphicsContext.restoreGraphicsState()
        try rep.representation(using:.png,properties:[:])!.write(to:directory.appendingPathComponent("icon_\(size)x\(size)\(scale == 2 ? "@2x" : "").png"))
    }
}
