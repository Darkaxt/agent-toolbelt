$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ExpectedSkills = @(
  @{ Name = "amazon-cli"; Path = "families/amazon-cli/codex/skills/amazon-cli/SKILL.md" },
  @{ Name = "skroutz-cli"; Path = "families/skroutz-cli/codex/skills/skroutz-cli/SKILL.md" },
  @{ Name = "aliexpress-cli"; Path = "families/aliexpress-cli/codex/skills/aliexpress-cli/SKILL.md" },
  @{ Name = "codex-thread-recall"; Path = "families/codex-thread-recall/codex/skills/codex-thread-recall/SKILL.md" },
  @{ Name = "everything-search"; Path = "families/everything/codex/skills/everything-search/SKILL.md" },
  @{ Name = "gemini-cli"; Path = "families/gemini/codex/skills/gemini-cli/SKILL.md" },
  @{ Name = "linkedin-cv"; Path = "families/linkedin-cv/codex/skills/linkedin-cv/SKILL.md" },
  @{ Name = "mail-domain-quarantine"; Path = "families/mail-domain-quarantine/codex/skills/mail-domain-quarantine/SKILL.md" },
  @{ Name = "yt-dlp-ffmpeg"; Path = "families/media/codex/skills/yt-dlp-ffmpeg/SKILL.md" },
  @{ Name = "observable-reputation"; Path = "families/observable-reputation/codex/skills/observable-reputation/SKILL.md" },
  @{ Name = "outlook-classic-mail"; Path = "families/outlook-classic-mail/codex/skills/outlook-classic-mail/SKILL.md" },
  @{ Name = "whatsapp-wacli"; Path = "families/whatsapp-wacli/codex/skills/whatsapp-wacli/SKILL.md" },
  @{ Name = "skills-sh-scout"; Path = "families/skills-sh-scout/codex/skills/skills-sh-scout/SKILL.md" }
)

function Fail($Message) {
  throw "skills.sh validation failed: $Message"
}

function Get-Frontmatter($Path) {
  $Text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  if ($Text -notmatch '(?s)^---\r?\n(.*?)\r?\n---') {
    Fail "missing YAML frontmatter in $Path"
  }
  return $Matches[1]
}

function Remove-Ansi($Text) {
  $Escape = [char]27
  return (($Text -join "`n") -replace "$Escape\[[0-9;?]*[ -/]*[@-~]", "")
}

function Assert-SkillCliOutput($Label, $Output) {
  $Output = Remove-Ansi $Output
  foreach ($Skill in $ExpectedSkills) {
    if ($Output -notmatch [regex]::Escape($Skill.Name)) {
      Fail "$Label did not list skill $($Skill.Name)"
    }
  }
  $ExpectedCount = $ExpectedSkills.Count
  if ($Output -notmatch "Found\D+$ExpectedCount\D+skills") {
    Fail "$Label did not report exactly $ExpectedCount discovered skills"
  }
}

Push-Location $RepoRoot
try {
  foreach ($Skill in $ExpectedSkills) {
    $SkillPath = Join-Path $RepoRoot $Skill.Path
    if (-not (Test-Path -LiteralPath $SkillPath)) {
      Fail "missing canonical skill file $($Skill.Path)"
    }
    $FolderName = Split-Path -Leaf (Split-Path -Parent $SkillPath)
    if ($FolderName -ne $Skill.Name) {
      Fail "skill folder $FolderName does not match name $($Skill.Name)"
    }

    $Frontmatter = Get-Frontmatter $SkillPath
    if ($Frontmatter -notmatch "(?m)^name:\s*$([regex]::Escape($Skill.Name))\s*$") {
      Fail "name mismatch in $($Skill.Path)"
    }
    if ($Frontmatter -notmatch "(?m)^description:\s*\S") {
      Fail "missing description in $($Skill.Path)"
    }
    if ($Frontmatter -notmatch "(?m)^license:\s*MIT\s*$") {
      Fail "missing MIT license metadata in $($Skill.Path)"
    }
    $HasCompatibility = (
      $Frontmatter -match "(?m)^compatibility:\s*\S" -or
      $Frontmatter -match "(?m)^\s+compatibility:\s*\S"
    )
    if (-not $HasCompatibility) {
      Fail "missing compatibility metadata in $($Skill.Path)"
    }
    if ($Frontmatter -notmatch "(?m)^\s+version:\s*`"0\.1\.0`"\s*$") {
      Fail "missing metadata.version in $($Skill.Path)"
    }
  }

  $ScanPaths = @("README.md", "docs/skills-sh.md") + ($ExpectedSkills | ForEach-Object { $_.Path })
  foreach ($RelativePath in $ScanPaths) {
    $Path = Join-Path $RepoRoot $RelativePath
    $Lines = Get-Content -LiteralPath $Path -Encoding UTF8
    for ($Index = 0; $Index -lt $Lines.Count; $Index++) {
      $Line = $Lines[$Index]
      if ($Line -match 'Users\\darka|darka-local') {
        Fail "local machine identity leaked in $RelativePath line $($Index + 1)"
      }
      if ($Line -match '[A-Za-z]:\\') {
        $Allowed = (
          $Line -match 'C:\\path\\' -or
          $Line -match 'C:\\snapshots\\' -or
          $Line -match 'C:\\temp\\' -or
          $Line -match 'C:\\Users\\<you>\\' -or
          $Line -match 'D:\\path\\'
        )
        if (-not $Allowed) {
          Fail "non-generic absolute path in $RelativePath line $($Index + 1)"
        }
      }
    }
  }

  $env:DISABLE_TELEMETRY = "1"
  $CurrentBranch = (& git branch --show-current 2>$null | Out-String).Trim()
  if ($CurrentBranch -eq "main") {
    $RemoteOutput = & npx --yes skills@1.5.10 add Darkaxt/agent-toolbelt --list 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
      Fail "remote skills CLI discovery failed"
    }
    Assert-SkillCliOutput "remote skills CLI discovery" $RemoteOutput
  } else {
    Write-Host "Skipping default-branch remote skills CLI discovery on feature branch $CurrentBranch."
  }

  $LocalOutput = & npx --yes skills@1.5.10 add . --list 2>&1 | Out-String
  if ($LASTEXITCODE -ne 0) {
    Fail "local skills CLI discovery failed"
  }
  Assert-SkillCliOutput "local skills CLI discovery" $LocalOutput

  Write-Host "skills.sh validation passed for $($ExpectedSkills.Count) skills."
} finally {
  Pop-Location
}
