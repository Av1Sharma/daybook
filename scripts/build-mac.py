#!/usr/bin/env python3
"""Build an offline, universal macOS Daybook.app and drag-to-install DMG."""
from pathlib import Path
import subprocess, shutil, plistlib, os, re
ROOT=Path(__file__).resolve().parents[1]
VERSION='1.1.0'
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
    plistlib.dump({'CFBundleExecutable':'Daybook','CFBundleIdentifier':'com.avisharma.daybook','CFBundleName':'Daybook','CFBundleDisplayName':'Daybook','CFBundlePackageType':'APPL','CFBundleShortVersionString':VERSION,'CFBundleVersion':'2','LSMinimumSystemVersion':'13.0','NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication','CFBundleIconFile':'Daybook.icns'},f)
cache=build/'ModuleCache';cache.mkdir(exist_ok=True)
for arch in ['arm64','x86_64']:
    subprocess.run(['swiftc','-O','-target',arch+'-apple-macos13.0','-module-cache-path',str(cache),str(ROOT/'macos/Daybook.swift'),'-o',str(build/('Daybook-'+arch))],check=True)
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
print(dmg)
