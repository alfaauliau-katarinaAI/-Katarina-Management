# Bootstrap from the extracted folder when not using connector deployment.
# The repository was created as -Katarina-Management (leading hyphen).
# Consider renaming and switching it to PRIVATE in GitHub settings.
$ErrorActionPreference = 'Stop'
$repository = 'https://github.com/alfaauliau-katarinaAI/-Katarina-Management.git'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw 'Git not installed.'
}
if (-not (Test-Path '.github/workflows/management.yml')) {
  throw 'Run from the extracted management folder.'
}
if (-not (Test-Path '.git')) { git init -b main }
git add README.md .gitignore SETUP-GITHUB.ps1 management config tests docs .github
if (git status --porcelain) {
  git -c user.name='Katarina Management Bootstrap' -c user.email='katarina-management@users.noreply.github.com' commit -m 'Update isolated management scheduler'
}
if (-not (git remote | Select-String '^origin$')) { git remote add origin $repository }
Write-Output ('Ready to push to '+$repository)
git push -u origin main
