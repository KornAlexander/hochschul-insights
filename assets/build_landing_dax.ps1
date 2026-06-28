# Converts landing.html into a DAX measure string for the
# "HTML Content" / "HTML Viewer" Power BI custom visual.
#
# - Strips <!doctype>, <html>, <head>, <body> wrappers (HTML Content injects a fragment).
# - Wraps everything in a single root <div> sized 1920x1080 (Full HD report page).
# - Escapes every " to "" for DAX string literal.
# - Writes Hochschul-Insights/assets/landing.dax with:  Landingpage = "<...>"
#
# Re-run after editing landing.html.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$src  = Join-Path $root 'landing.html'
$dst  = Join-Path $root 'landing.dax'

$html = [System.IO.File]::ReadAllText($src, [System.Text.UTF8Encoding]::new($false))

# Extract <style>...</style> block
$styleMatch = [regex]::Match($html, '(?is)<style\b[^>]*>(.*?)</style>')
$styleCss   = if ($styleMatch.Success) { $styleMatch.Groups[1].Value } else { '' }

# Extract body innerHTML
$bodyMatch = [regex]::Match($html, '(?is)<body\b[^>]*>(.*?)</body>')
$bodyHtml  = if ($bodyMatch.Success) { $bodyMatch.Groups[1].Value } else { $html }

# Scope the CSS to .landing-root so it cannot leak into the host page.
# The actual stage now uses position:fixed; inset:0 so it always fills the
# entire HTML Content visual regardless of iframe height quirks.
# We strip the html,body rule entirely (PBI's host already styles them) so we
# don't conflict with the visual's own document.
$styleCss = $styleCss -replace '(?is)html,\s*body\s*\{[^}]*\}', ''

# Assemble fragment: wrapper exists only as a logical container — the .stage
# inside uses position:fixed; inset:0, so it overlays the entire visual area.
$fragment = @"
<div class="landing-root">
<style>
$styleCss
</style>
$bodyHtml
</div>
"@

# Collapse whitespace between tags (optional, keeps DAX string shorter)
# $fragment = [regex]::Replace($fragment, '>\s+<', '><')

# DAX escape: " -> ""
$escaped = $fragment -replace '"', '""'

$measure = "Landingpage =`r`n`"$escaped`""

[System.IO.File]::WriteAllText($dst, $measure, [System.Text.UTF8Encoding]::new($false))

Write-Host "Wrote $dst  ($($measure.Length) chars)"
