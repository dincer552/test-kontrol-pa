"""Self-updater for Test Control, using the same manifest/chunk model as PDF kW Selector."""
from __future__ import annotations
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request

UPDATE_MANIFEST_URL = "http://20.91.245.7/test-kontrol-updates/manifest.json"

def _get_json(url):
    req = urllib.request.Request(url, headers={"Accept":"application/json","User-Agent":"Test-Kontrol-Updater","Cache-Control":"no-cache"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))

def _sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def _version_tuple(value):
    try: return tuple(int(x) for x in str(value or "").strip().lstrip("vV").split("."))
    except ValueError: return ()

def check_for_update(current_version, current_build_sha=""):
    manifest=_get_json(UPDATE_MANIFEST_URL)
    remote_version=str(manifest.get("version") or "")
    remote_build=str(manifest.get("build") or "").lower()
    current_build=str(current_build_sha or "").lower()
    same_version=bool(_version_tuple(current_version)) and bool(_version_tuple(remote_version)) and _version_tuple(current_version)>=_version_tuple(remote_version)
    same_build=bool(remote_build and current_build) and remote_build==current_build
    base=UPDATE_MANIFEST_URL.rsplit("/",1)[0]+"/"
    return {"version":remote_version or "latest","build_sha":remote_build,"download_url":base+str(manifest["file"]),"asset_size":int(manifest.get("size") or 0),"digest":str(manifest.get("sha256") or "").lower(),"chunks":[{"url":base+str(x["file"]),"size":int(x["size"])} for x in (manifest.get("chunks") or [])],"available":not(same_version or same_build)}

def _download_chunks(chunks,target):
    def fetch(item):
        index,chunk=item; expected=int(chunk["size"])
        for _ in range(5):
            req=urllib.request.Request(chunk["url"],headers={"User-Agent":"Test-Kontrol-Updater","Cache-Control":"no-cache"})
            with urllib.request.urlopen(req,timeout=120) as response: data=response.read()
            if len(data)==expected: return index,data
        raise RuntimeError(f"Güncelleme parçası eksik: {len(data)}/{expected} bayt")
    pending={}; next_index=0
    with Path(target).open("wb") as out:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(fetch,item) for item in enumerate(chunks)]
            for future in as_completed(futures):
                index,data=future.result(); pending[index]=data
                while next_index in pending: out.write(pending.pop(next_index)); next_index+=1

def download_update(info,progress_callback=None):
    fd,raw=tempfile.mkstemp(prefix="test_kontrol_update_",suffix=".exe"); os.close(fd); target=Path(raw)
    try:
        chunks=info.get("chunks") or []; expected_size=int(info.get("asset_size") or 0)
        if chunks:
            _download_chunks(chunks,target); done=target.stat().st_size
            if expected_size and done!=expected_size: raise RuntimeError(f"Güncelleme eksik indirildi: {done}/{expected_size} bayt")
            if progress_callback: progress_callback(done,expected_size)
        else:
            req=urllib.request.Request(info["download_url"],headers={"User-Agent":"Test-Kontrol-Updater"})
            with urllib.request.urlopen(req,timeout=180) as response, target.open("wb") as out:
                total=int(response.headers.get("Content-Length") or expected_size or 0); done=0
                while True:
                    data=response.read(1024*1024)
                    if not data: break
                    out.write(data); done+=len(data)
                    if progress_callback: progress_callback(done,total)
        if target.stat().st_size<=0: raise RuntimeError("İndirilen EXE boş.")
        actual=_sha256(target); expected=str(info.get("digest") or "").replace("sha256:","").lower()
        if expected and actual.lower()!=expected: raise RuntimeError(f"SHA-256 doğrulaması başarısız: {actual}")
        return target
    except Exception:
        target.unlink(missing_ok=True); raise

def restart_with_update(temp_exe,target_exe=None):
    target=Path(target_exe or sys.executable).resolve()
    if os.name!="nt" or not getattr(sys,"frozen",False): raise RuntimeError("Güncelleme yalnızca paketlenmiş Windows EXE üzerinden çalışır.")
    fd,raw_script=tempfile.mkstemp(prefix="test_kontrol_update_",suffix=".ps1"); os.close(fd); script=Path(raw_script)
    script.write_text(r'''
param([string]$Source, [string]$Target, [int]$ParentPid, [string]$ScriptPath)
$ErrorActionPreference = "Stop"
try {
    for ($i = 0; $i -lt 120; $i++) {
        if (-not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    if (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) { throw "Eski program kapatılamadı." }
    for ($i = 0; $i -lt 60; $i++) {
        try {
            Move-Item -LiteralPath $Source -Destination $Target -Force -ErrorAction Stop
            Start-Process -FilePath $Target
            break
        } catch {
            if ($i -eq 59) { throw }
            Start-Sleep -Seconds 1
        }
    }
} catch {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        ("Güncelleme kurulamadı. Programı kapatıp tekrar deneyin." + [Environment]::NewLine + [Environment]::NewLine + $_.Exception.Message),
        "TEST KONTROL güncellemesi",
        [System.Windows.MessageBoxButton]::OK,
        [System.Windows.MessageBoxImage]::Error
    ) | Out-Null
} finally {
    Remove-Item -LiteralPath $ScriptPath -Force -ErrorAction SilentlyContinue
}
'''.strip(),encoding="utf-8-sig")
    subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-WindowStyle","Hidden","-File",str(script),str(temp_exe),str(target),str(os.getpid()),str(script)],close_fds=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    raise SystemExit(0)
