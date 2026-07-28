# Read the text currently visible in the FOCUSED window and emit it as JSON.
#
# Two independent sources, because they fail in opposite ways:
#   * UI Automation walks the accessibility tree. Exact and cheap, and it reaches
#     things OCR can't infer — a browser's address bar, an input's real value.
#     Blank in apps that render their own UI without exposing it.
#   * OCR reads pixels via Windows.Media.Ocr. Works on anything you can see, at
#     ~300ms, with no structure and occasional character errors.
#
# Deliberately scoped to the focused window, not the whole desktop: less noise for
# the model, a smaller context bill, and a much smaller privacy blast radius. The
# screenshot goes to a temp file (the WinRT decoder needs a path) and is deleted in
# `finally` — captures are never left on disk.
#
# -Serve runs a long-lived worker: one JSON line out per line of stdin in. Use it.
# A cold start costs ~1.2s in process spawn and Add-Type alone, which dwarfs the
# ~300ms of actual work; amortised, a read lands in ~350ms.
#
#   powershell -File scripts/read-screen.ps1                # one shot
#   powershell -File scripts/read-screen.ps1 -Serve         # worker on stdin
param(
    [switch]$Serve,
    [switch]$NoOcr,
    [switch]$NoUia,
    [int]$MaxChars = 4000
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Add-Type -AssemblyName System.Drawing, System.Windows.Forms, System.Runtime.WindowsRuntime
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class Win {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  public static string Title(IntPtr h) { var sb = new StringBuilder(512); GetWindowText(h, sb, 512); return sb.ToString(); }
  public static uint Pid(IntPtr h) { uint p; GetWindowThreadProcessId(h, out p); return p; }
}
'@

# WinRT async shim for Windows PowerShell 5.1: grab the generic
# AsTask<T>(IAsyncOperation<T>) overload once and invoke it per result type.
$script:AsTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($op, $type) {
    $t = $script:AsTask.MakeGenericMethod($type).Invoke($null, @($op))
    $t.Wait(-1) | Out-Null
    $t.Result
}

# Force WinRT projections to load now rather than on first read.
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime]
$script:Engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()

# ------------------------------------------------------------- UIA filtering --

# Raw UIA values are mostly junk for our purposes: Electron apps expose
# vscode-webview:// and vscode-file:// URLs with session ids, which are pure
# context burn. Keep real http(s) URLs (a browser's address bar is the single most
# useful thing here) and short human-readable strings. Drop everything else.
function Test-UsefulUia([string]$v) {
    if (-not $v) { return $false }
    $v = $v.Trim()
    if ($v.Length -lt 2) { return $false }
    if ($v -match '^(vscode-|devtools|blob:|data:|about:|chrome-extension:)') { return $false }
    if ($v -match '^https?://') { return $v.Length -le 300 }
    if ($v.Length -gt 120) { return $false }          # a wall of text: OCR's job
    if ($v -match '^[0-9a-f]{16,}$') { return $false } # bare hashes / ids
    return $true
}

function Get-UiaText($hwnd) {
    try {
        $el = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
        $cond = New-Object System.Windows.Automation.OrCondition(
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::Edit)),
            (New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::Document))
        )
        # Children only, not Descendants: a full tree walk on a big app can take
        # seconds, and the address bar / main document sit near the top anyway.
        $found = $el.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
        $keep = New-Object System.Collections.Generic.List[string]
        $seen = New-Object System.Collections.Generic.HashSet[string]
        foreach ($node in $found) {
            $v = $null
            try { $v = $node.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value } catch {}
            if (-not $v) { $v = $node.Current.Name }
            if ((Test-UsefulUia $v) -and $seen.Add($v.Trim())) { $keep.Add($v.Trim()) }
            if ($keep.Count -ge 8) { break }
        }
        return ($keep -join " | ")
    } catch {
        return ""
    }
}

# -------------------------------------------------------------------- snapshot --

function Get-ScreenSnapshot {
    $hwnd = [Win]::GetForegroundWindow()
    if ($hwnd -eq [IntPtr]::Zero) { return @{ ok = $false; error = "no foreground window" } }

    $r = New-Object Win+RECT
    if (-not [Win]::GetWindowRect($hwnd, [ref]$r)) { return @{ ok = $false; error = "GetWindowRect failed" } }

    $procId = [Win]::Pid($hwnd)
    $app = ""
    try { $app = (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch {}

    # Clamp to the virtual screen: a maximised window reports a few px of
    # invisible border, and a negative origin breaks CopyFromScreen.
    $vs = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $x = [Math]::Max($r.L, $vs.X); $y = [Math]::Max($r.T, $vs.Y)
    $w = [Math]::Min($r.R, $vs.X + $vs.Width) - $x
    $h = [Math]::Min($r.B, $vs.Y + $vs.Height) - $y

    $out = [ordered]@{
        ok = $true; app = $app; title = [Win]::Title($hwnd)
        rect = @{ x = $x; y = $y; w = $w; h = $h }
        uia = ""; ocr = ""; ocr_ms = 0; truncated = $false; error = ""
    }

    if (-not $NoUia) { $out.uia = Get-UiaText $hwnd }

    if (-not $NoOcr -and $script:Engine -and $w -gt 20 -and $h -gt 20) {
        $tmp = Join-Path $env:TEMP ("deskavatar-ocr-" + [Guid]::NewGuid().ToString("N") + ".png")
        try {
            $bmp = New-Object System.Drawing.Bitmap($w, $h)
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $g.CopyFromScreen($x, $y, 0, 0, $bmp.Size)
            $bmp.Save($tmp, [System.Drawing.Imaging.ImageFormat]::Png)
            $g.Dispose(); $bmp.Dispose()

            $sw = [Diagnostics.Stopwatch]::StartNew()
            $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($tmp)) ([Windows.Storage.StorageFile])
            $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
            $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $sb = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            $res = Await ($script:Engine.RecognizeAsync($sb)) ([Windows.Media.Ocr.OcrResult])
            $sw.Stop()

            $out.ocr = ((@($res.Lines) | ForEach-Object { $_.Text }) -join "`n")
            $out.ocr_ms = [int]$sw.ElapsedMilliseconds
            $stream.Dispose()
        } catch {
            $out.error = $_.Exception.Message
        } finally {
            # Screen captures are never left on disk.
            if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
        }
    }

    if ($out.ocr.Length -gt $MaxChars) {
        $out.ocr = $out.ocr.Substring(0, $MaxChars)
        $out.truncated = $true
    }
    return $out
}

function Write-Snapshot($snap) {
    [Console]::Out.WriteLine(($snap | ConvertTo-Json -Compress -Depth 6))
    [Console]::Out.Flush()
}

# ------------------------------------------------------------------- entry --

if ($Serve) {
    # Signal readiness so the caller knows Add-Type is done and the next read
    # will be fast.
    Write-Snapshot @{ ok = $true; ready = $true; ocr_available = [bool]$script:Engine }
    while ($null -ne ($line = [Console]::In.ReadLine())) {
        if ($line.Trim() -eq "") { continue }
        if ($line.Trim() -eq "quit") { break }
        try { Write-Snapshot (Get-ScreenSnapshot) }
        catch { Write-Snapshot @{ ok = $false; error = $_.Exception.Message } }
    }
} else {
    Write-Snapshot (Get-ScreenSnapshot)
}
