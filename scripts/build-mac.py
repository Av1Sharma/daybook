#!/usr/bin/env python3
"""Build an offline, universal macOS Daybook.app and drag-to-install DMG."""
from pathlib import Path
import subprocess, shutil, plistlib, os, re, json, hashlib
ROOT=Path(__file__).resolve().parents[1]
VERSION='1.2.0'
build=ROOT/'build'; release=ROOT/'release'; app=build/'Daybook.app'
if app.exists():shutil.rmtree(app)
resources=app/'Contents/Resources'; binaries=app/'Contents/MacOS'
resources.mkdir(parents=True); binaries.mkdir(parents=True);release.mkdir(exist_ok=True)
html=(ROOT/'dist/index.html').read_text()
css=(ROOT/'dist/style.css').read_text()
parts=[]
for name in ['model.mjs','screenshot-data.mjs','internships.mjs','app.js']:
    js=(ROOT/'dist'/name).read_text()
    js=re.sub(r'^import .*?;\n','',js,flags=re.M)
    js=re.sub(r'\bexport (?=(?:const|function|class)\b)','',js)
    parts.append(js)
js='\n'.join(parts).replace('</script','<\\/script')
html=html.replace('<link rel="stylesheet" href="style.css">','<style>'+css+'</style>').replace('<script type="module" src="app.js"></script>','')
html=html.replace('</body>','<script type="module">'+js+'</script></body>')
(resources/'index.html').write_text(html)
with (app/'Contents/Info.plist').open('wb') as f:
    plistlib.dump({'CFBundleExecutable':'Daybook','CFBundleIdentifier':'com.avisharma.daybook','CFBundleName':'Daybook','CFBundleDisplayName':'Daybook','CFBundlePackageType':'APPL','CFBundleShortVersionString':VERSION,'CFBundleVersion':'3','LSMinimumSystemVersion':'13.0','NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication','CFBundleIconFile':'Daybook.icns'},f)
cache=build/'ModuleCache';cache.mkdir(exist_ok=True)
shared=[ROOT/'macos/Updates/UpdateCore.swift',ROOT/'macos/Updates/UpdatePublicKey.swift',ROOT/'macos/Updates/InstallCore.swift']
for arch in ['arm64','x86_64']:
    for name, files in [('Daybook',[ROOT/'macos/Daybook.swift',ROOT/'macos/Updates/Updater.swift',*shared]),('DaybookInstaller',[ROOT/'macos/Updates/InstallerMain.swift',*shared])]:
        subprocess.run(['swiftc','-O','-target',arch+'-apple-macos13.0','-module-cache-path',str(cache),*map(str,files),'-o',str(build/(name+'-'+arch))],check=True)
subprocess.run(['lipo','-create',str(build/'DaybookInstaller-arm64'),str(build/'DaybookInstaller-x86_64'),'-output',str(binaries/'DaybookInstaller')],check=True)
subprocess.run(['codesign','--force','--sign','-',str(binaries/'DaybookInstaller')],check=True)
subprocess.run(['lipo','-create',str(build/'Daybook-arm64'),str(build/'Daybook-x86_64'),'-output',str(binaries/'Daybook')],check=True)
subprocess.run(['swift','-module-cache-path',str(cache),str(ROOT/'macos/Icon.swift'),str(build/'Daybook.iconset')],check=True)
subprocess.run(['iconutil','-c','icns',str(build/'Daybook.iconset'),'-o',str(resources/'Daybook.icns')],check=True)
subprocess.run(['codesign','--force','--sign','-','--identifier','com.avisharma.daybook',str(app)],check=True)
subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
stage=build/'dmg-stage'
if stage.exists():shutil.rmtree(stage)
stage.mkdir();shutil.copytree(app,stage/'Daybook.app',symlinks=True)
(stage/'Applications').symlink_to('/Applications')
(stage/'Read me.txt').write_text('Daybook '+VERSION+'\n\nDrag Daybook into Applications and open it.\nYour notebook stays on your Mac in ~/Library/Application Support/Daybook/notebook.json.\nScreenshot data is imported once; subsequent launches preserve your changes.\n\nThis personal release is ad-hoc signed, not Apple-notarized. macOS may require approval in System Settings > Privacy & Security on first launch.\n\nBack up your notebook using the in-app Back up notebook button.\n')
dmg=release/('Daybook-'+VERSION+'-universal.dmg')
subprocess.run(['hdiutil','create','-volname','Daybook','-srcfolder',str(stage),'-ov','-format','UDZO',str(dmg)],check=True)
subprocess.run(['hdiutil','verify',str(dmg)],check=True)
archive=release/'Daybook-update.zip'
if archive.exists():archive.unlink()
subprocess.run(['ditto','-c','-k','--keepParent',str(app),str(archive)],check=True)
manifest={'version':VERSION,'minimumSystemVersion':'13.0.0','archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'size':archive.stat().st_size}
(release/'daybook-update.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
subprocess.run(['swiftc','-module-cache-path',str(cache),str(ROOT/'scripts/SignUpdate.swift'),'-o',str(build/'daybook-sign-update')],check=True)
subprocess.run([str(build/'daybook-sign-update'),'sign',str(release/'daybook-update.json'),str(release/'daybook-update.sig'),str(ROOT/'macos/Updates/public-key.txt')],check=True)
(release/('SHA256SUMS-'+VERSION+'.txt')).write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in [dmg,archive,release/'daybook-update.json',release/'daybook-update.sig']))
print(dmg)
