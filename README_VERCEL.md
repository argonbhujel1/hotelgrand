# Hotel Grand Garden — Vercel Deploy

## Files
- app1.py, config.py, index1.html, admin1.html, requirements.txt, vercel.json

## Required Environment Variables (Vercel → Settings → Environment Variables)

| Key | Value |
|-----|--------|
| DATABASE_URL | PostgreSQL URL (Neon / Supabase free) |
| SECRET_KEY | random long string |
| CLOUDINARY_URL | cloudinary://API_KEY:API_SECRET@CLOUD_NAME |

## Deploy
1. Push to GitHub
2. Vercel → New Project → Import repo
3. Framework: Other
4. Add env vars above
5. Deploy

## Notes
- SQLite will NOT persist on Vercel — use Postgres (Neon free: https://neon.tech)
- Images must use Cloudinary
- Free Vercel has cold starts & 10s function timeout
- Admin: admin@hotelgrandgarden.com / admin123 (change after first login)

## Local
```
pip install -r requirements.txt
python app1.py
```
