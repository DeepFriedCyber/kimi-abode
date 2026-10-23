# 🗄️ Rebuild PostgreSQL Database for Kimi Abode

**Goal:** Fix PostgreSQL connection issues and enable full production functionality  
**Prerequisites:** PostgreSQL 14+ installed and running on localhost:5432

---

## 🔍 Current Problem

Your `.env` currently uses SQLite fallback:
```env
DATABASE_URL=sqlite:./api/data.db
```

To use PostgreSQL (for full vector search, persistence, scalability):
```env
DATABASE_URL=postgresql://abode:<ROTATE-ME-db-password>@localhost:5432/abode
```

**Issue:** Authentication failures due to misconfigured `pg_hba.conf`

---

## ✅ Step-by-Step Fix

### Step 1: Verify PostgreSQL is Running

```powershell
# Check if PostgreSQL service is running
Get-Service -Name "*postgresql*" | Select-Object Name, Status

# Or check port 5432
netstat -ano | findstr :5432
```

**Expected:** Service should be `Running` and port `LISTENING`

---

### Step 2: Create Database and User

#### Option A: Using pgAdmin (GUI) — Recommended for Windows

1. Open pgAdmin → Connect to PostgreSQL server
2. Right-click **Databases** → **Create** → **Database**
   - Name: `abode`
   - Owner: `postgres` (or leave default)
3. Right-click **Roles** → **Create** → **Role**
   - Name: `abode`
   - Login/Password: `<ROTATE-ME-db-password>`
   - Privileges: Read/Write to database

#### Option B: Using psql Command Line

```powershell
# Connect as superuser
psql -U postgres -d postgres

# Inside psql prompt:
CREATE DATABASE abode;
CREATE USER abode WITH PASSWORD '<ROTATE-ME-db-password>';
GRANT ALL PRIVILEGES ON DATABASE abode TO abode;
\q
```

---

### Step 3: Fix pg_hba.conf Authentication

**File Location:** `C:\Program Files\PostgreSQL\data\pg_hba.conf`  
(or find location with: `Get-ChildItem -Path "C:\Program Files\PostgreSQL" -Filter "pg_hba.conf"`)

**Edit the file and add these lines at the end:**
```conf
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     trust                   # Socket connections
host    all             all             127.0.0.1/32            trust                    # IPv4 localhost
host    all             all             ::1/128                 trust                     # IPv6 localhost
```

**Important:** Lines should NOT have `md5` or `scram-sha-256` at the end for local connections.

**Reload PostgreSQL:**
```powershell
net stop postgresql-x64-16   # Adjust version if different (e.g., 14, 15)
net start postgresql-x64-16
```

---

### Step 4: Verify Connection Works

```powershell
psql "postgresql://abode:<ROTATE-ME-db-password>@localhost:5432/abode" -c "SELECT version();"
```

**Expected:** PostgreSQL version string returned successfully

---

### Step 5: Run Migration Script

The migration script is ready at `migrations/migrate.ts`:

```bash
cd api
npm run migrate
```

**Or manually:**
```powershell
# From project root
npx ts-node migrations/migrate.ts
```

**Expected Output:**
```
[Migration] Checking database connection...
[Migration] Database initialized with tables: properties
[Migration] Database seeded
```

---

### Step 6: Update Environment Configuration

Edit `.env`:

```env
# Change from SQLite to PostgreSQL
DATABASE_URL=postgresql://abode:<ROTATE-ME-db-password>@localhost:5432/abode

# Strong JWT secret (minimum 32 characters)
JWT_SECRET=your-very-long-super-secret-random-string-minimum-32-chars-here

# Development mode — set to "true" for in-memory store
DEVELOPMENT_MODE=false
```

---

### Step 7: Restart API Server

```bash
# Stop current server (Ctrl+C in terminal)

# Start with new configuration
cd api
npm run dev
```

**Expected Output:**
```
[API] Environment variables loaded
[PropertyRepository] Attempting PostgreSQL connection...
[PropertyRepository] PostgreSQL connected successfully
[Migration] Checking database connection...
[Migration] Database initialized
```

---

## 🧪 Test Full Functionality

### 1. Search Endpoint Test
```bash
curl "http://localhost:3001/api/search?q=cabin"
```

**Expected:** Returns properties from PostgreSQL database

### 2. AI Service Integration
```bash
curl -X POST http://localhost:3001/api/parse \
  -H "Content-Type: application/json" \
  -d '{"query":"cabin in uk"}'
```

**Expected:** Returns parsed query with intent and entities

---

## 📊 Migration Script Details

The `migrations/migrate.ts` script:

1. Creates PostgreSQL connection pool
2. Defines schema for `properties` table
3. Seeds sample properties
4. Handles conflicts gracefully (upsert on address)
5. Logs all operations for debugging

**To add more properties:** Edit the `sampleProperties` array in the migration script

---

## 🔒 Security Checklist (After Rebuild)

- [ ] JWT_SECRET is at least 32 characters
- [ ] pg_hba.conf uses trust for local connections (or scram-sha-256 for network)
- [ ] Database has principle of least privilege
- [ ] API server runs behind reverse proxy with HTTPS
- [ ] CORS_ORIGIN configured for production

---

## 🚨 Troubleshooting

### Connection Refused
```powershell
# Check PostgreSQL is listening on correct port
netstat -ano | findstr :5432

# If not running, start service
net start postgresql-x64-16
```

### Authentication Failed
```powershell
# Verify pg_hba.conf settings
Get-Content "C:\Program Files\PostgreSQL\data\pg_hba.conf" | Select-String "all.*trust"

# Reload PostgreSQL after changes
net stop postgresql-x64-16
net start postgresql-x64-16
```

### User Does Not Exist
```powershell
psql -U postgres -c "SELECT usename FROM pg_user WHERE usename='abode';"
```

**If empty:** Run Step 2 again to create user

---

## ✅ Success Criteria

You'll know PostgreSQL is working when:

1. API logs show "PostgreSQL connected successfully"
2. Search returns properties from database (not empty array)
3. Migration script completes without errors
4. No fallback to in-memory store

---

**Alternative:** If PostgreSQL setup is too complex, stick with SQLite — it works perfectly for development and testing!

**See:** `CODE_REVIEW_IMPROVEMENTS.md` for alternative improvements.