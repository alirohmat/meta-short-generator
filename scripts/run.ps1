Set-Location $PSScriptRoot/..
if (Test-Path ".env") {
  Get-Content ".env" | ForEach-Object {
    if ($_ -match "^\s*([^#=]+)=(.*)$") { Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim() }
  }
}
pip install -q -r requirements.txt
python main.py @args
