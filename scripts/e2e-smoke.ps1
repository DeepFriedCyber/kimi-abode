$ErrorActionPreference = "Continue"
$root = "C:\Users\aps33\Projects\Kimi-Abode"
$results = @()

function Record($name, $value) {
  $script:results += [pscustomobject]@{ Check = $name; Result = $value }
}

$ai = $null
$api = $null

try {
  $ai = Start-Process -FilePath "python" `
    -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8001" `
    -WorkingDirectory "$root\ai-service" -PassThru `
    -RedirectStandardOutput "$env:TEMP\ai.out" -RedirectStandardError "$env:TEMP\ai.err"

  $api = Start-Process -FilePath "node" `
    -ArgumentList "--import","tsx","src/index.ts" `
    -WorkingDirectory "$root\api" -PassThru `
    -RedirectStandardOutput "$env:TEMP\api.out" -RedirectStandardError "$env:TEMP\api.err"

  # Wait for the AI service
  $aiReady = $false
  for ($i = 0; $i -lt 40; $i++) {
    try {
      $h = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health" -TimeoutSec 2
      if ($h.status) { $aiReady = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
  }
  Record "ai-health" ($(if ($aiReady) { "ok ($($h.mode), db=$($h.db))" } else { "FAILED" }))

  # Wait for the gateway
  $apiReady = $false
  for ($i = 0; $i -lt 40; $i++) {
    try {
      $g = Invoke-RestMethod -Uri "http://127.0.0.1:3001/health" -TimeoutSec 2
      if ($g.status) { $apiReady = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
  }
  Record "api-health" ($(if ($apiReady) { "ok (v$($g.version))" } else { "FAILED" }))

  if (-not ($aiReady -and $apiReady)) {
    Write-Output "--- api stderr ---"
    Get-Content "$env:TEMP\api.err" -ErrorAction SilentlyContinue | Select-Object -Last 20
    throw "services did not start"
  }

  # Aggregate health through the gateway
  $agg = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/health" -TimeoutSec 10
  Record "gateway->ai" "$($agg.services.ai_service.status) / db:$($agg.services.database.status)"

  # Search through the gateway (AI has no Postgres -> demo fixture)
  $search = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/search?q=3%20bed%20in%20Sandbach&min_beds=3&limit=5" -TimeoutSec 20
  Record "search" "status=200 tier=$($search.tier_used) returned=$($search.properties.Count) total=$($search.total_matches)"
  Record "search-fields" (($search.properties[0].PSObject.Properties.Name) -join ",")
  Record "search-geo" "town=$($search.properties[0].town) postcode=$($search.properties[0].postcode) lat=$($search.properties[0].latitude) floor=$($search.properties[0].floor_area_sqm) psm=$($search.properties[0].price_per_sqm)"

  # Structured filters against the imported dataset
  $bungalows = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/search?q=in%20Sandbach&property_type=bungalow&limit=10" -TimeoutSec 20
  $types = ($bungalows.properties | ForEach-Object { $_.property_type } | Sort-Object -Unique) -join ","
  Record "filter-type" "returned=$($bungalows.properties.Count) types=$types"

  $cheap = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/search?q=in%20Crewe&max_price=150000&limit=10" -TimeoutSec 20
  $maxPrice = ($cheap.properties | Measure-Object price_paid -Maximum).Maximum
  Record "filter-price" "returned=$($cheap.properties.Count) max_price=$maxPrice total=$($cheap.total_matches)"

  # POI data served from the preloaded OSM extract cache
  $poi = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:3001/api/ask/poi" `
    -ContentType "application/json" `
    -Body '{"lat":53.097675,"lon":-2.405048,"n":5}' -TimeoutSec 20
  $first = $poi.nearby | Select-Object -First 1
  Record "poi-nearby" "count=$($poi.nearby.Count) first=$($first.name) ($($first.category), $($first.distance_m)m) scores=$($poi.category_scores.PSObject.Properties.Name.Count)"

  # Agent listing import (multipart through the gateway)
  $csvPath = Join-Path $env:TEMP "e2e-listings.csv"
  @(
    "Address,Town,Postcode,Price,Bedrooms,Type,Description",
    '"99 Demo Upload Road, CW11 1JD",Sandbach,CW11 1JD,499950,5,Detached,"Uploaded by the e2e test"'
  ) | Set-Content -Path $csvPath -Encoding UTF8

  $preview = & curl.exe -sS -m 60 -X POST "http://127.0.0.1:3001/api/listings/import" `
    -H "x-agent-id: e2e-agent" `
    -F "file=@$csvPath;type=text/csv" -F "dry_run=true" 2>&1 | Out-String | ConvertFrom-Json
  Record "upload-preview" "format=$($preview.format) received=$($preview.received) valid=$($preview.valid) imported=$($preview.imported)"

  $committed = & curl.exe -sS -m 60 -X POST "http://127.0.0.1:3001/api/listings/import" `
    -H "x-agent-id: e2e-agent" `
    -F "file=@$csvPath;type=text/csv" -F "dry_run=false" 2>&1 | Out-String | ConvertFrom-Json
  Record "upload-commit" "imported=$($committed.imported) geocoded=$($committed.geocoded)"

  $uploaded = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/search?q=Demo%20Upload%20Road&limit=50" -TimeoutSec 20
  $match = $uploaded.properties | Where-Object { $_.address_line1 -eq "99 Demo Upload Road" } | Select-Object -First 1
  Record "upload-searchable" "found=$([bool]$match) price=$($match.asking_price) status=$($match.listing_status) total=$($uploaded.total_matches)"

  $listingPage = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/listings?limit=5" -TimeoutSec 10
  Record "listings-list" "total=$($listingPage.total)"

  # Listing photos (multipart, processed to WebP, EXIF stripped).
  # A random colour gives a unique content hash, so "added" is meaningful on
  # a database that survives between runs.
  $imagePath = Join-Path $env:TEMP "e2e-photo.jpg"
  python -c "import random; from PIL import Image; Image.new('RGB', (900, 600), tuple(random.randrange(256) for _ in range(3))).save(r'$imagePath', 'JPEG')"
  $listingId = ($listingPage.listings | Where-Object { $_.address_line1 -eq "99 Demo Upload Road" } | Select-Object -First 1).id

  $photoUpload = & curl.exe -sS -m 60 -X POST "http://127.0.0.1:3001/api/listings/$listingId/photos" `
    -H "x-agent-id: e2e-agent" -F "files=@$imagePath;type=image/jpeg" 2>&1 | Out-String | ConvertFrom-Json
  Record "photo-upload" "added=$($photoUpload.added) total=$($photoUpload.total)"

  $photoUpload2 = & curl.exe -sS -m 60 -X POST "http://127.0.0.1:3001/api/listings/$listingId/photos" `
    -H "x-agent-id: e2e-agent" -F "files=@$imagePath;type=image/jpeg" 2>&1 | Out-String | ConvertFrom-Json
  Record "photo-idempotent" "added=$($photoUpload2.added) total=$($photoUpload2.total)"

  $photo = $photoUpload.photos | Select-Object -First 1
  $mediaInfo = & curl.exe -sS -o "$env:TEMP\e2e-photo.webp" -w "%{http_code} %{content_type}" -m 20 "http://127.0.0.1:3001/api$($photo.url)" 2>&1
  Record "photo-media" "$mediaInfo bytes=$((Get-Item "$env:TEMP\e2e-photo.webp").Length)"

  $propertyWithPhotos = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/property/$listingId" -TimeoutSec 10
  Record "photo-on-property" "photos=$($propertyWithPhotos.photos.Count) cover=$($propertyWithPhotos.photos[0].is_cover)"

  # Area Q&A (deterministic, from the OSM cache)
  $supermarket = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/property/1/nearby?q=nearest%20supermarket" -TimeoutSec 20
  Record "area-supermarket" "answer=$($supermarket.answer) results=$($supermarket.results.Count)"

  $tesco = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/property/1/nearby?q=how%20far%20is%20the%20nearest%20Tesco%3F" -TimeoutSec 20
  Record "area-brand" "brand=$($tesco.intent.brand) first=$($tesco.results[0].name) dist=$($tesco.results[0].distance_m)m fallback=$([bool]$tesco.fallback)"

  $gyms = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/property/1/nearby?q=what%20gyms%20are%20nearby%3F" -TimeoutSec 20
  $gymCategories = ($gyms.results | ForEach-Object { $_.category } | Sort-Object -Unique) -join ","
  Record "area-gyms" "results=$($gyms.results.Count) categories=$gymCategories"

  $areaStatus = & curl.exe -sS -o "$env:TEMP\area.json" -w "%{http_code}" -m 15 "http://127.0.0.1:3001/api/property/1/nearby?q=what%20is%20stamp%20duty" 2>&1
  Record "area-non-amenity" "status=$areaStatus"

  $areaChat = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:3001/api/chat" -ContentType "application/json" `
    -Body '{"messages":[{"role":"user","content":"how far is the nearest supermarket?"}],"property_id":1}' -TimeoutSec 20
  Record "area-chat" "has_llm=$($areaChat.has_llm) mentions=$($areaChat.response -match 'supermarket|Aldi')"

  $templateStatus = & curl.exe -sS -o "$env:TEMP\template.csv" -w "%{http_code}" -m 10 "http://127.0.0.1:3001/api/listings/import/template?format=csv" 2>&1
  Record "upload-template" "status=$templateStatus bytes=$((Get-Item "$env:TEMP\template.csv").Length)"

  # Parse through the gateway
  $parse = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:3001/api/parse" `
    -ContentType "application/json" `
    -Body '{"query":"3 bed semi-detached in Sandbach under 250k"}' -TimeoutSec 20
  Record "parse" "beds=$($parse.min_beds) max_price=$($parse.max_price) location=$($parse.location) types=$($parse.property_types -join '|')"

  # Validation must be a 400 with a structured body
  try {
    Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/search" -TimeoutSec 5 | Out-Null
    Record "validation" "FAILED (expected 400)"
  } catch {
    $body = $_.ErrorDetails.Message | ConvertFrom-Json
    Record "validation" "400 error='$($body.error)' issues=$($body.details.Count)"
  }

  # Auth round-trip
  $email = "e2e-$([guid]::NewGuid().ToString('N').Substring(0,8))@example.com"
  $reg = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:3001/api/auth/register" `
    -ContentType "application/json" `
    -Body (@{ email = $email; password = "a long e2e passphrase"; name = "E2E" } | ConvertTo-Json) -TimeoutSec 10
  Record "register" "201 id=$($reg.user.id)"

  $login = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:3001/api/auth/login" `
    -ContentType "application/json" `
    -Body (@{ email = $email; password = "a long e2e passphrase" } | ConvertTo-Json) -TimeoutSec 10
  Record "login" "token-len=$($login.access_token.Length)"

  $me = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/auth/me" -Headers @{ Authorization = "Bearer $($login.access_token)" } -TimeoutSec 10
  Record "me" $me.user.email

  # Wrong password must be 401 and identical to unknown user
  try {
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:3001/api/auth/login" -ContentType "application/json" `
      -Body (@{ email = $email; password = "wrong passphrase" } | ConvertTo-Json) | Out-Null
    Record "bad-login" "FAILED (expected 401)"
  } catch {
    Record "bad-login" "401 as expected"
  }

  # Chat SSE through the gateway (curl: Invoke-WebRequest mangles streams)
  $chatRaw = & curl.exe -sS -N -m 30 -X POST "http://127.0.0.1:3001/api/chat/stream" `
    -H "Content-Type: application/json" `
    -d '{\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]}' 2>&1 | Out-String
  $hasDone = $chatRaw -match "\[DONE\]"
  $frames = ([regex]::Matches($chatRaw, "data: ")).Count
  Record "chat-stream" "frames=$frames done=$hasDone"

  # Metrics
  $metrics = & curl.exe -sS -m 5 "http://127.0.0.1:3001/api/metrics" 2>&1 | Out-String
  Record "metrics" "lines=$(($metrics -split "`n").Count) has-counter=$($metrics -match 'abode_http_')"

  # Property without a database -> upstream 503 mapped to 502 with a generic body
  $propertyStatus = & curl.exe -sS -o "$env:TEMP\property.json" -w "%{http_code}" -m 10 "http://127.0.0.1:3001/api/property/1" 2>&1
  $propertyBody = Get-Content "$env:TEMP\property.json" -Raw -ErrorAction SilentlyContinue
  Record "property" "status=$propertyStatus body=$propertyBody"
}
catch {
  Record "EXCEPTION" $_.Exception.Message
}
finally {
  if ($api) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
  if ($ai) { Stop-Process -Id $ai.Id -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Milliseconds 500
}

$results | Format-Table -AutoSize | Out-String -Width 200
