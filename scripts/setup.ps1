param(
  [ValidateSet('cloud-text','cloud-local-voice','local-text','local-voice')][string]$Profile = 'local-voice',
  [ValidateSet('9b','4b')][string]$Model = '9b',
  [switch]$DryRun,
  [switch]$InstallNative,
  [switch]$SkipModels
)
$ErrorActionPreference = 'Stop'
$TaskProjectRoot = Split-Path -Parent $PSScriptRoot
if ($DryRun) {
  $TaskPreviewArgs = @("$TaskProjectRoot/scripts/setup_environment.py", '--profile', $Profile, '--model', $Model, '--dry-run')
  if (Get-Command python -ErrorAction SilentlyContinue) { & python @TaskPreviewArgs }
  elseif (Get-Command py -ErrorAction SilentlyContinue) { & py -3 @TaskPreviewArgs }
  else { throw 'Preview requires an existing Python 3 interpreter; it will not download one.' }
  exit $LASTEXITCODE
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' }
$TaskSetupArgs = @('run','--no-project','--python','3.13',"$TaskProjectRoot/scripts/setup_environment.py",'--profile',$Profile,'--model',$Model)
if ($DryRun) { $TaskSetupArgs += '--dry-run' }
if ($InstallNative) { $TaskSetupArgs += '--install-native' }
if ($SkipModels) { $TaskSetupArgs += '--skip-models' }
& uv @TaskSetupArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
