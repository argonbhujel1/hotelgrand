"""
Hotel Grand Garden - Configuration
"""
import os
import tempfile
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _database_uri():
    """Prefer DATABASE_URL (Neon / Supabase / Render Postgres). Fix postgres:// to postgresql://"""
    url = os.environ.get('DATABASE_URL') or os.environ.get('SQLALCHEMY_DATABASE_URI')
    if url:
        # Some providers give postgres:// which SQLAlchemy rejects
        if url.startswith('postgres://'):
            url = url.replace('postgres://', 'postgresql://', 1)
        return url
    return 'sqlite:///' + os.path.join(BASE_DIR, 'hotel.db')


def _upload_folder():
    """
    Vercel (and most serverless) have a read-only filesystem.
    Only /tmp is writable. Use /tmp/uploads on Vercel, local static/uploads otherwise.
    """
    if os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
        return os.path.join(tempfile.gettempdir(), 'uploads')
    return os.path.join(BASE_DIR, 'static', 'uploads')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hotel-grand-garden-secret-key-2024-secure'
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = _upload_folder()
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Hotel defaults
    HOTEL_NAME = "Hotel Grand Garden Family Restaurant and Bar"
    HOTEL_PHONE = "9816374804"
    HOTEL_LOCATION = "Urlabari-5, Morang, Nepal"
    CURRENCY = "Rs"
    WHATSAPP_NUMBER = "9816374804"
