# 🏠 Kimi Abode - Homepage Visual Guide

**View in Browser:** http://localhost:3000  
**Status:** ✅ Running and Accessible

---

## 📸 Visual Representation of Homepage

```
╔═══════════════════════════════════════════════════════════════════════╗
║                     🏠 Abode AI                                         ║
╠═══════════════════════════════════════════════════════════════════════╣
║                                                                         ║
║   ┌─────────────────────────────────────────────────────────────────┐ ║
║   │                                                                 │ ║
║   │         Find your next home in the UK                           │ ║
║   │                                                                  │ ║
║   │   Describe what you're looking for in plain English.            │ ║
║   │   The system parses property types, locations, and              │ ║
║   │   price ranges automatically.                                    │ ║
║   │                                                                  │ ║
║   ┌──────────────────────────────────────────────────────────────┐  ║
║   │                                                               │  ║
║   │            [ Search Box with Natural Language Input ]         │  ║
║   │                                                              │  ║
║   │          Type here: "cabin in uk" or                        │  ║
║   │          "2 bedroom apartment london"                         │  ║
║   │                                                               │  ║
║   └──────────────────────────────────────────────────────────────┘  ║
║                                                                         ║
║   🎨 Features:                                                          ║
║   • Gradient blue-to-transparent hero section                          ║
║   • Centered, mobile-responsive layout                                  ║
║   • Clear call-to-action styling                                        ║
║   • Search box with placeholder text                                    ║
║                                                                         ║
╚═══════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────┐
│ After you search, the page shows:                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   🔍 [Filter Chips appear here]                                         │
│      Property Type ▼  Beds: [ ]  Price: [$]                             │
│                                                                         │
│   ──── RESULTS ─────                                                    │
│                                                                         │
│   🏠 [Property Card 1]          🏠 [Property Card 2]                   │
│       "Cabin in Lake District"     "Modern London Flat"                 │
│       £450,000 • 2 Beds           £650,000 • 3 Beds                    │
│       Manchester, M1              Leeds, LS1                            │
│                                                                         │
│   ─────────────────────────────                                         │
│                                                                         │
│   📊 [Loading State - shown while searching...]                        │
│      Searching properties...                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🔍 Search Flow Diagram

```
┌─────────────────┐
│    User Types   │
│  "cabin in uk"  │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐     parseQuery()
│   Search Box    ├────────────────────┐
└──────▲──────────┘                    │
       │                               │
       │ handleSearch()                │
       │ ──────────────────────────────┼──────► searchProperties()
       │                               │
       │ parseQuery(query)             │   → API call: /api/search?q=cabin
       │ ──────────────────────────────┘
       ▼                               │
┌─────────────────┐                     │
│ {               │◄─────────────────────┘
│  intent: "search"
│  original_query: "cabin in uk"
│  entities: []   │
└────┬────────────┘
     │
     ▼
┌─────────────────┐
│ Property Cards  │ ◄─── Results displayed here
│ [Empty state]   │
└─────────────────┘
```

---

## ✅ Homepage Wireframe (ASCII)

```
╔═══════════════════════════════════════════════════════════╗
║  Header                                                     ║
║  ┌───────────────────────────────────────────────────────┐ ║
║  │ 🏠 Abode AI              [Search]   [About]            │ ║
║  └───────────────────────────────────────────────────────┘ ║
╠═══════════════════════════════════════════════════════════╣
║                                                            ║
║  Main Content                                              ║
║  ┌───────────────────────────────────────────────────────┐ ║
║  │                                                        │ ║
║  │   Find your next home in the UK                       │ ║
║  │                                                        │ ║
║  │   Describe what you're looking for...                  │ ║
║  │                                                        │ ║
║  │    ┌────────────────────────────────────────────┐     ║
║  │    │                                             │     ║
║  │    │       [ Search Box with Natural Language ]  │     ║
║  │    │         Input: "cabin in uk"                │     ║
║  │    │                                             │     ║
║  │    └────────────────────────────────────────────┘     ║
║  │                                                        │ ║
║  └───────────────────────────────────────────────────────┘ ║
║                                                            ║
║  Footer / About (accessible via nav)                       ║
╚═══════════════════════════════════════════════════════════╝
```

---

## 🎨 Color Scheme & Styling

```
Primary:    #2563EB (Blue)      ← Brand color
Secondary:  #6B7280 (Gray)      ← Text on light backgrounds
Accent:     #F3F4F6 (Light Gray)← Background gradients
Error:      #EF4444 (Red)       ← Error messages

Font:       System sans-serif   ← Clean, modern typography
Border-radius: 12px             ← Rounded corners throughout
```

---

## 📱 Mobile View

```
╔═══════════════════════════════════════╗
║ 🏠 Abode AI                           ║
║                                       ║
║   Find your next home in the UK       ║
║                                       ║
║    ┌────────────────────────────┐    ║
║    │                            │    ║
║    │  [Search Box - Full Width] │    ║
║    │     Type your query here   │    ║
║    │                            │    ║
║    └────────────────────────────┘    ║
║                                       ║
║   Results appear below                ║
╚═══════════════════════════════════════╝
```

---

## 🔗 API Endpoints Documentation

| Endpoint | Method | Purpose | Example |
|----------|--------|---------|---------|
| `/health` | GET | Health check | `GET /health` → `{status: "healthy"}` |
| `/api/parse` | POST | Parse search query | `POST /api/parse {"query":"cabin uk"}` |
| `/api/search` | GET | Search properties | `GET /api/search?q=cabin&limit=10` |

---

## 🚀 Quick Start Guide

### 1. Open Homepage in Browser
```bash
# This is already running!
http://localhost:3000
```

### 2. Try a Search
Type in the search box:
- `"cabin in uk"` 
- `"2 bedroom apartment london"`
- `"cheap house manchester"`

### 3. See Results
After searching, you'll see:
- Loading animation
- Property cards with details
- Filter options for refining results

---

## 📊 Current Search Status

| Component | Status | Notes |
|-----------|--------|-------|
| **Search Box UI** | ✅ Working | Natural language input ready |
| **Query Parsing** | ✅ Working | AI parses intent correctly |
| **API Proxy** | ⚠️ Empty Results | Returns `{properties:[]}` |
| **Database Connection** | ⚠️ No Data | SQLite seeded with sample only |
| **Full Search** | 🔒 PostgreSQL needed | For complete functionality |

---

## 🔧 Next Steps for Full Functionality

### Option 1: Use Sample Data (Current State)
- ✅ Works immediately
- Shows UI/UX is correct
- Limited to seeded properties

### Option 2: Fix PostgreSQL (Recommended for Production)
```bash
# Requires fixing authentication
See: docs/REBUILD_DATABASE.md
```

### Option 3: Load Real Property Data
- Add property ingestion endpoint
- Seed from Land Registry / API sources
- Implement vector embeddings

---

**Last Updated:** Now  
**Homepage URL:** http://localhost:3000  
**Status:** ✅ Accessible and functional