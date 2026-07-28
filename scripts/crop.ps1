# Crop a region out of a PNG. Companion to screenshot.ps1 — a 2560x1440 desktop
# grab is mostly empty space when all you want to look at is a 120px character.
#
#   powershell -ExecutionPolicy Bypass -File scripts/crop.ps1 in.png out.png 0 1140 2560 300 [scale]
param(
    [Parameter(Mandatory = $true)][string]$In,
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$X = 0, [int]$Y = 0, [int]$W = 400, [int]$H = 400,
    [double]$Scale = 1.0
)

Add-Type -AssemblyName System.Drawing

$src = [System.Drawing.Image]::FromFile((Resolve-Path $In))
$W = [Math]::Min($W, $src.Width - $X)
$H = [Math]::Min($H, $src.Height - $Y)

$dw = [int]($W * $Scale); $dh = [int]($H * $Scale)
$dst = New-Object System.Drawing.Bitmap($dw, $dh)
$g = [System.Drawing.Graphics]::FromImage($dst)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$g.DrawImage($src, (New-Object System.Drawing.Rectangle(0, 0, $dw, $dh)),
    (New-Object System.Drawing.Rectangle($X, $Y, $W, $H)),
    [System.Drawing.GraphicsUnit]::Pixel)
$dst.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $dst.Dispose(); $src.Dispose()

Write-Output "$Out (${dw}x${dh})"
