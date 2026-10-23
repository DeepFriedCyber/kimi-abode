$ErrorActionPreference = "Continue"
$root = "C:\Users\aps33\Projects\Kimi-Abode"
$ai = $null; $api = $null; $web = $null

try {
  $ai = Start-Process python -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8001" -WorkingDirectory "$root\ai-service" -PassThru -RedirectStandardOutput "$env:TEMP\f-ai.out" -RedirectStandardError "$env:TEMP\f-ai.err"
  $api = Start-Process node -ArgumentList "--import","tsx","src/index.ts" -WorkingDirectory "$root\api" -PassThru -RedirectStandardOutput "$env:TEMP\f-api.out" -RedirectStandardError "$env:TEMP\f-api.err"
  $web = Start-Process node -ArgumentList "node_modules/next/dist/bin/next","start","-p","3000" -WorkingDirectory "$root\frontend" -PassThru -RedirectStandardOutput "$env:TEMP\f-web.out" -RedirectStandardError "$env:TEMP\f-web.err"

  for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-RestMethod "http://127.0.0.1:3000/" -TimeoutSec 3 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 }
  }

  $homePage = & curl.exe -sS -m 15 "http://127.0.0.1:3000/" 2>&1 | Out-String
  "home: html=$($homePage -match '<html') hero=$($homePage -match 'Find a home by describing it') css-link=$($homePage -match '_next/static/css')"

  $cssHref = [regex]::Match($homePage, 'href="([^"]*_next/static/css/[^"]+)"').Groups[1].Value
  if ($cssHref) {
    $css = & curl.exe -sS -m 15 "http://127.0.0.1:3000$cssHref" 2>&1 | Out-String
    "css: bytes=$($css.Length) property-grid=$($css -match 'property-grid') utility-classes=$($css -match '\.bg-white')"
  }

  $searchPage = & curl.exe -sS -m 20 "http://127.0.0.1:3000/search?q=bungalow%20in%20Sandbach" 2>&1 | Out-String
  "search page: html=$($searchPage -match '<html') heading=$($searchPage -match 'Property search')"

  $detailPage = & curl.exe -sS -m 20 "http://127.0.0.1:3000/property/1" 2>&1 | Out-String
  "detail page: html=$($detailPage -match '<html') shell=$($detailPage -match 'Loading property')"

  $chunkHit = Get-ChildItem -Recurse "$root\frontend\.next\static\chunks\app\property" -Filter *.js -ErrorAction SilentlyContinue |
    Select-String -Pattern "Ask about this area" -SimpleMatch -List
  "area qa: bundled=$([bool]$chunkHit)"

  $agentPage = & curl.exe -sS -m 20 "http://127.0.0.1:3000/agent/import" 2>&1 | Out-String
  "agent import: html=$($agentPage -match '<html') heading=$($agentPage -match 'Import listings') dropzone=$($agentPage -match 'Drag a file here')"

  $myListings = & curl.exe -sS -m 20 "http://127.0.0.1:3000/agent/listings" 2>&1 | Out-String
  "agent listings: html=$($myListings -match '<html') heading=$($myListings -match 'My listings')"
}
finally {
  if ($web) { Stop-Process -Id $web.Id -Force -ErrorAction SilentlyContinue }
  if ($api) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
  if ($ai) { Stop-Process -Id $ai.Id -Force -ErrorAction SilentlyContinue }
}
