#!/usr/bin/env pwsh
<#
Demo script: compare ugrep vs ripgrep (rg) on Windows PowerShell (pwsh).

Creates a small demo tree, then runs a series of search commands with both
tools and prints labeled outputs so you can compare behavior and flags.

Usage: run in pwsh: .\scripts\compare_ugrep_rg.ps1

This script will NOT modify files outside the demo folder.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Ensure-Dir([string]$p){ if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null } }

$root = Join-Path $PSScriptRoot 'demo_data'
if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force }
Ensure-Dir $root

Write-Host "Creating demo files under: $root`n"

Set-Content -LiteralPath (Join-Path $root 'file1.txt') -Value @(
    'Hello world',
    'This file mentions avif and AVIF.',
    'Line with Avif in mixed case',
    'Another line with hello'
)

Set-Content -LiteralPath (Join-Path $root 'file2.log') -Value @(
    'Log start',
    'no image here',
    'avif appears here too'
)

Ensure-Dir (Join-Path $root 'sub')
Set-Content -LiteralPath (Join-Path $root 'sub\note.md') -Value @(
    '# Notes',
    'A markdown file that does not mention the magic word.'
)

# filename with space
Set-Content -LiteralPath (Join-Path $root 'space file.txt') -Value @(
    'a file whose name contains spaces',
    'it mentions avif once'
)

# small binary file
[byte[]]$b = 0..255
[IO.File]::WriteAllBytes((Join-Path $root 'binary.bin'), $b)

# zip containing a text file (tests Compress-Archive availability)
$zipPath = Join-Path $root 'sample.zip'
Compress-Archive -Path (Join-Path $root 'sub\*') -DestinationPath $zipPath -Force

function HasCmd($name){ return (Get-Command $name -ErrorAction SilentlyContinue) -ne $null }

function RunBlock($title, $cmd){
    Write-Host "`n=== $title ===" -ForegroundColor Cyan
    Write-Host "Command: $cmd`n" -ForegroundColor DarkCyan
    try{
        $out = Invoke-Expression $cmd 2>&1
        if ($null -eq $out -or $out.Count -eq 0) { Write-Host "<no output>" -ForegroundColor DarkYellow }
        else { $out | ForEach-Object { Write-Host $_ } }
    } catch {
        Write-Host "<error running command: $($_.Exception.Message)>" -ForegroundColor Red
    }
}

# Helper to run the two commands if available
function CompareCase($title, $ugrepCmd, $rgCmd){
    Write-Host "`n#########################" -ForegroundColor Green
    Write-Host "# $title" -ForegroundColor Green
    Write-Host "#########################`n" -ForegroundColor Green

    if (HasCmd 'ugrep') { RunBlock 'ugrep' $ugrepCmd } else { Write-Host "ugrep not found — skipping" -ForegroundColor Yellow }
    if (HasCmd 'rg')    { RunBlock 'rg (ripgrep)' $rgCmd }    else { Write-Host "rg not found — skipping" -ForegroundColor Yellow }
}

# Use $root as search base. Wrap paths with single quotes for safety when building strings.
$base = "'" + $root + "'"

### Test cases ###

CompareCase 'Basic recursive, case-insensitive search for "avif"' \
    "ugrep -n -r -i --include=\"*.txt\" --include=\"*.log\" 'avif' $base" \
    "rg -n -i -g '*.txt' -g '*.log' 'avif' $base"

CompareCase 'List files that contain the match (-l)' \
    "ugrep -l -r -i --include=\"*.txt\" 'avif' $base" \
    "rg -l -i -g '*.txt' 'avif' $base"

CompareCase 'List files that do NOT contain the match (-L)' \
    "ugrep -L -r -i --include=\"*.txt\" 'avif' $base" \
    "rg -L -i -g '*.txt' 'avif' $base"

CompareCase 'Count matches per file (-c)' \
    "ugrep -c -r --include=\"*.txt\" 'avif' $base" \
    "rg -c -g '*.txt' 'avif' $base"

CompareCase 'Null-separated filenames (safe for spaces) and convert to absolute paths' \
    "ugrep -0 -l -r --include=\"*.txt\" 'avif' $base | ForEach-Object { if ($_ -ne '') { Resolve-Path -LiteralPath $_ } }" \
    "rg -0 -l -g '*.txt' 'avif' $base | ForEach-Object { if ($_ -ne '') { Resolve-Path -LiteralPath $_ } }"

CompareCase 'PCRE (-P) example: alternation and word boundaries' \
    "ugrep -n -P -r --include=\"*.txt\" '\\b(avif|AVIF)\\b' $base" \
    "rg -n -P -g '*.txt' '\\b(avif|AVIF)\\b' $base"

CompareCase 'Context lines (-C, -A, -B)' \
    "ugrep -n -C2 -r --include=\"*.txt\" 'Hello' $base" \
    "rg -n -C2 -g '*.txt' 'Hello' $base"

CompareCase 'Treat binary as text (-a) and search binary content' \
    "ugrep -a -n -r '255' $base" \
    "rg -a -n '255' $base"

CompareCase 'Include / Exclude patterns' \
    "ugrep -n -r --include=\"*.md\" --exclude=\"file2.log\" 'Notes' $base" \
    "rg -n -g '*.md' -g '!file2.log' 'Notes' $base"

CompareCase 'Show formatted output (ugrep --format) vs rg color' \
    "ugrep -n --color=always --format=\"%n:%f:%l\" -r --include=\"*.txt\" 'avif' $base" \
    "rg --color=always -n -g '*.txt' 'avif' $base"

Write-Host "`nDemo finished. If a tool was missing, install it and re-run the script." -ForegroundColor Magenta

Write-Host "Notes:`n - This script demonstrates common flags and equivalent rg flags but is not exhaustive.`n - ugrep supports additional advanced formats and file-type magic; consult their manpages for full coverage." -ForegroundColor DarkGray
