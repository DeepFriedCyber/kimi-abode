# Kimi Abode - Production Deployment Checklist

## Pre-Deployment Verification

### Environment Setup ✅
- [ ] Copy `.env.example` to `.env` and configure production values
- [ ] Set `JWT_SECRET` with minimum 64 characters (generate with: `openssl rand -base64 32`)
- [ ] Configure `DATABASE_URL` with strong password (min 16 chars)
- [ ] Set `NODE_ENV=production`
- [ ] Configure CORS origins for production domains

### API Gateway Configuration ✅
- [ ] `JWT_SECRET=<secure_random_64_plus_chars>` - **CRITICAL**
- [ ] `DATABASE_URL=postgresql://user:strong_password@host:port/database?sslmode=require`
- [ ] `CORS_ORIGIN=https://your-production-domain.com` (comma-separated)
- [ ] `AI_SERVICE_URL=<ai-service-url>`

### AI Service Configuration ✅
- [ ] `DATABASE_URL=postgresql://...` with SSL if production
- [ ] `ANTHROPIC_API_KEY=<key>` if using Claude (recommended for safety)
- [ ] `AI_DB_POOL_MIN=2`, `AI_DB_POOL_MAX=10` - Prevent pool exhaustion

### Database Setup ✅
- [ ] PostgreSQL instance running and accessible
- [ ] Migration files applied successfully
- [ ] SSL certificates configured (production only)

## Code Quality & Security Verification

### Security Fixes Applied ✅
- [x] JWT secret validation (min 32 chars, warn on <64 chars)
- [x] Argon2 password hashing with OWASP parameters (timeCost=3, memoryCost=64MB)
- [x] Cryptographically secure token generation (crypto.randomFillSync)
- [x] Database connection pool limits (max 10 connections)
- [x] CORS origin whitelisting in production mode

### Type Safety Fixes Applied ✅
- [x] Removed all `any | undefined` types
- [x] Proper error handling with try/catch/finally
- [x] NaN/Infinity guards for numeric displays

### Stability Fixes Applied ✅
- [x] WebSocket rate limiting (5 messages/minute)
- [x] AI service timeout handling (30s default)
- [x] Bounded SSE buffers (~2MB max)
- [x] Health check caching with stale-while-revalidate

## Deployment Steps

### 1. Database Setup
```bash
# PostgreSQL
docker-compose up -d postgres
# Wait for migrations to complete
sleep 5
```

### 2. API Gateway
```bash
cd api
npm install
cp .env.example .env
# Edit .env with production values
npm run build
npm start
```

**Verify**: `curl http://localhost:3001/health` → `{ "status": "ok", "mode": "read-write" }`

### 3. AI Service
```bash
cd ai-service
pip install -r requirements.txt
cp .env.example .env
# Edit .env with production values
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

**Verify**: `curl http://localhost:8001/health` → `{ "status": "ok", "db": true }`

### 4. Frontend
```bash
cd frontend
npm install
cp .env.example .env.local
# Edit with production API URL
npm run build
npm start
```

**Verify**: Visit `https://your-production-domain.com` in browser

## Post-Deployment Monitoring

### Health Checks
- [ ] Monitor `/metrics` endpoint for request counts
- [ ] Verify WebSocket connections via browser dev tools
- [ ] Check database connection pool utilization

### Logs to Monitor
- Database connection errors
- JWT validation failures
- CORS configuration mismatches
- Rate limiting triggers (normal, not an error)

### Performance Benchmarks
- Property search response time: < 1s
- WebSocket message latency: < 200ms
- Health check cache hit rate: > 50%

## Security Hardening Options (Post-Launch)

### Recommended Enhancements
1. **Enable HTTPS with Let's Encrypt**
   ```bash
   sudo apt install certbot python3-certbot-nginx
   # Configure auto-renewal
   ```

2. **Add Redis Cache**
   - For session storage if moving from JWT cookies
   - For property search result caching

3. **Implement Request Rate Limiting at Gateway**
   - Add `@fastify/rate-limit` plugin
   - Set global limits per endpoint

4. **Enable Database Audit Logging**
   - Track sensitive queries (user creation/deletion)

5. **Set Up Monitoring Stack**
   - Prometheus + Grafana for metrics
   - Sentry or LogRocket for error tracking

## Troubleshooting Guide

### "Missing required environment variables"
→ Run `cp .env.example .env` and verify all required vars are set

### "argon2 is required for password hashing"
→ Install: `cd api && npm install argon2`

### "CORS policy blocked a request"
→ Verify frontend origin matches CORS_ORIGIN in API config

### WebSocket connections fail
→ Check AI_SERVICE_URL connectivity and rate limiting logs

### Database connection errors
→ Verify DATABASE_URL format and PostgreSQL service status

## Rollback Plan

If issues occur:
1. Keep previous version tagged in git
2. Restore old `.env` files from backup
3. Restart services with `npm start` / `uvicorn`

## Contact & Escalation

For critical incidents:
- Check health endpoints first
- Review application logs
- Escalate to on-call if database unresponsive

---

**Status**: Ready for deployment ✅  
**Last Updated**: 2024-12-28  
**Code Review Sign-off**: All security fixes implemented and verified