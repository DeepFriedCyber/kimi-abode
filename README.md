# Kimi Abode - Property Search Application

A 3-tier property search application with AI-powered semantic parsing and POI intelligence:
- **Frontend**: Next.js (React) with TypeScript
- **API Gateway**: Fastify (TypeScript/Node.js)
- **AI Service**: FastAPI (Python) + PostgreSQL database

## Architecture

```
┌─────────────┐      HTTP/WebSocket      ┌─────────────┐
│  Frontend   │ ◄──────────────────►     │   API       │
│  (Next.js)  │                          │  (Fastify)  │
└─────────────┘                          └─────────────┘
                                            │
                                            ▼ HTTP/SSE
                                    ┌─────────────┐
                                    │  AI Service  │
                                    │(FastAPI + ML)│
                                    └─────────────┘
```

## Quick Start

### Development Setup

1. Copy environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. Start the API server (TypeScript/Fastify):
   ```bash
   cd api
   npm install
   npm run dev
   ```

3. Start the frontend (Next.js):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. Visit `http://localhost:3000` in your browser.

## Security Best Practices

### JWT Secret Generation

Generate a cryptographically secure JWT secret:
```bash
# Using openssl (recommended)
openssl rand -base64 32

# Using Node.js
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"

# Using Python
python -c "import os; print(os.urandom(32).hex())"
```

### Database Security

- Never use weak passwords in production
- Use environment variables for secrets
- Enable SSL/TLS for database connections in production

### CORS Configuration

The application automatically hardens CORS:
- **Development**: Allows `http://localhost:*`
- **Production**: Only whitelisted HTTPS origins are allowed

Set `CORS_ORIGIN` in `.env`:
```bash
# Development
CORS_ORIGIN=http://localhost:3000

# Production (comma-separated HTTPS origins)
CORS_ORIGIN=https://app.abode-ai.local,https://kimi-abode.local
```

### Password Hashing

Argon2id is used with OWASP-recommended parameters:
- **timeCost**: 3 iterations
- **memoryCost**: 64MB (65536 KB)
- **parallelism**: 4 threads

## Database Configuration

The application supports PostgreSQL for persistent storage:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/abode
```

**Without DATABASE_URL**: Uses in-memory storage for development (data lost on restart).

**With DATABASE_URL**: Full persistence with authentication.

## Rate Limiting

- **WebSocket messages**: 5 per minute per connection
- **API requests**: 100 per minute by default

## Health Checks

The API provides health status:
```bash
curl http://localhost:3001/api/health
```

## Error Handling

### Frontend Error Boundaries

Components wrapped with error boundaries will display a recovery UI instead of crashing the app.

### Database Connection Pool

- Max connections: 10
- Idle timeout: 30 seconds
- Connection timeout: 2 seconds

## Troubleshooting

### "Missing required environment variables"

Run `cp .env.example .env` and ensure all required variables are set.

### "argon2 is required for password hashing"

Install the package:
```bash
cd api && npm install argon2
```

### CORS errors

Check that your frontend origin matches `CORS_ORIGIN` in `.env`.

## License

MIT