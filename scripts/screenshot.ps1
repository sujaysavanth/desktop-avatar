# Grab the whole virtual desktop to a PNG. Dev helper for eyeballing the avatar
# where it actually lives — on the desktop, over other windows — since nothing
# about a transparent always-on-top window shows up in a normal window capture.
#
#   powershell -ExecutionPolicy Bypass -File scripts/screenshot.ps1 out.png
param([string]$Out = "$env:TEMP\desk-avatar.png")

Add-Type -AssemblyName System.Windows.Forms, System.Drawing

$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()

Write-Output "$Out ($($b.Width)x$($b.Height))"
