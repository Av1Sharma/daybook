import Foundation
import CryptoKit
import Security

let service = "com.avisharma.daybook.release-signing"
let account = "ed25519-v1"
func load(create: Bool) throws -> Curve25519.Signing.PrivateKey {
    let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:service,kSecAttrAccount as String:account,kSecReturnData as String:true,kSecMatchLimit as String:kSecMatchLimitOne]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecSuccess, let data = result as? Data { return try Curve25519.Signing.PrivateKey(rawRepresentation:data) }
    guard status == errSecItemNotFound && create else { throw NSError(domain:"DaybookSigning",code:Int(status),userInfo:[NSLocalizedDescriptionKey:"The update signing key is unavailable in Keychain. No new key was created."]) }
    let key = Curve25519.Signing.PrivateKey()
    let record:[String:Any] = [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:service,kSecAttrAccount as String:account,kSecValueData as String:key.rawRepresentation,kSecAttrAccessible as String:kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
    let added=SecItemAdd(record as CFDictionary,nil)
    guard added == errSecSuccess else { throw NSError(domain:"DaybookSigning",code:Int(added)) }
    return key
}
do {
    let args=CommandLine.arguments
    let key=try load(create:args.count==2 && args[1]=="initialize")
    if args.count==2 && args[1]=="initialize" {print(key.publicKey.rawRepresentation.base64EncodedString())}
    else if args.count==5 && args[1]=="sign" {
        let expected=try String(contentsOfFile:args[4],encoding:.utf8).trimmingCharacters(in:.whitespacesAndNewlines)
        guard key.publicKey.rawRepresentation.base64EncodedString()==expected else {throw NSError(domain:"DaybookSigning",code:1,userInfo:[NSLocalizedDescriptionKey:"Keychain key does not match the pinned update key."])}
        let signature=try key.signature(for:Data(contentsOf:URL(fileURLWithPath:args[2])))
        try (signature.base64EncodedString()+"\n").write(toFile:args[3],atomically:true,encoding:.utf8)
    } else {throw NSError(domain:"DaybookSigning",code:2,userInfo:[NSLocalizedDescriptionKey:"Usage: initialize OR sign manifest signature public-key-file"])}
} catch { fputs("Signing failed: \(error.localizedDescription)\n",stderr);exit(1) }
