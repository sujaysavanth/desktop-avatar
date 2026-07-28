# Probe: can we read text off the screen with ZERO model and ZERO VRAM?
#
# Windows ships an OCR engine (Windows.Media.Ocr). If this works it's a far better
# fit for a local-first desk pet than a vision model: no weights to load, no VRAM
# to compete with the chat model for, and it returns the *actual* text rather than
# a model's guess at it.
#
#   powershell -ExecutionPolicy Bypass -File scripts/ocr-probe.ps1 <image.png>
param([Parameter(Mandatory = $true)][string]$Image)

Add-Type -AssemblyName System.Runtime.WindowsRuntime

# WinRT async in Windows PowerShell 5.1 needs this shim: grab the generic
# AsTask<T>(IAsyncOperation<T>) overload and invoke it per result type.
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($op, $type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}

# Force the WinRT projections to load.
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime]

$sw = [Diagnostics.Stopwatch]::StartNew()

$path = (Resolve-Path $Image).Path
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { Write-Error "no OCR engine for the current user languages"; exit 1 }

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$sw.Stop()

$lines = @($result.Lines)
Write-Output "engine language : $($engine.RecognizerLanguage.LanguageTag)"
Write-Output "image           : $($decoder.PixelWidth)x$($decoder.PixelHeight)"
Write-Output "elapsed         : $([int]$sw.ElapsedMilliseconds) ms"
Write-Output "lines found     : $($lines.Count)"
Write-Output "words found     : $(($lines | ForEach-Object { @($_.Words).Count } | Measure-Object -Sum).Sum)"
Write-Output "--- first 15 lines ---"
$lines | Select-Object -First 15 | ForEach-Object { Write-Output "  $($_.Text)" }
