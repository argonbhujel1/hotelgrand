"""
Hotel Grand Garden Family Restaurant and Bar
Hotel Management & Online Booking System
Flask + SQLite + Bootstrap 5
"""
import os
import json
import secrets
from datetime import datetime, timedelta, date
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template_string, request, redirect, url_for,
    flash, session, jsonify, send_from_directory, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
for sub in ['rooms', 'gallery', 'slider', 'menu', 'amenities', 'general', 'reviews']:
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], sub), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
# media_url registered after function def via before_request or below

login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'


# Cloudinary — set CLOUDINARY_URL or CLOUDINARY_CLOUD_NAME + API_KEY + API_SECRET on Render
CLOUDINARY_ENABLED = False
try:
    import cloudinary
    import cloudinary.uploader
    from urllib.parse import urlparse

    _curl = os.environ.get('CLOUDINARY_URL', '').strip()
    _cn = (os.environ.get('CLOUDINARY_CLOUD_NAME') or os.environ.get('CLOUDINARY_CLOUD') or '').strip()
    _ck = (os.environ.get('CLOUDINARY_API_KEY') or '').strip()
    _cs = (os.environ.get('CLOUDINARY_API_SECRET') or '').strip()

    if _curl:
        # Format: cloudinary://API_KEY:API_SECRET@CLOUD_NAME
        os.environ['CLOUDINARY_URL'] = _curl  # SDK also reads this
        parsed = urlparse(_curl)
        # username=api_key, password=api_secret, hostname=cloud_name
        if parsed.hostname and parsed.username and parsed.password:
            cloudinary.config(
                cloud_name=parsed.hostname,
                api_key=parsed.username,
                api_secret=parsed.password,
                secure=True,
            )
            CLOUDINARY_ENABLED = True
            print('Cloudinary ENABLED (parsed CLOUDINARY_URL) cloud=', parsed.hostname)
        else:
            # Let SDK parse CLOUDINARY_URL from env
            cloudinary.config(secure=True)
            CLOUDINARY_ENABLED = True
            print('Cloudinary ENABLED (env CLOUDINARY_URL)')
    elif _cn and _ck and _cs:
        cloudinary.config(cloud_name=_cn, api_key=_ck, api_secret=_cs, secure=True)
        CLOUDINARY_ENABLED = True
        print('Cloudinary ENABLED cloud=', _cn)
    else:
        print('Cloudinary DISABLED — set CLOUDINARY_URL on Render Environment')
except Exception as _e:
    CLOUDINARY_ENABLED = False
    print('Cloudinary init error:', _e)

# ===================== MODELS =====================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='customer')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    bookings = db.relationship('Booking', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Setting(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    room_type = db.Column(db.String(50))
    beds = db.Column(db.String(100))
    max_guests = db.Column(db.Integer, default=2)
    price_weekday = db.Column(db.Float, default=0)
    price_weekend = db.Column(db.Float, default=0)
    discount_percent = db.Column(db.Float, default=0)
    amenities = db.Column(db.Text)
    images = db.Column(db.Text)
    is_available = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bookings = db.relationship('Booking', backref='room', lazy=True)

    def get_images(self):
        try:
            return json.loads(self.images or '[]')
        except Exception:
            return []

    def set_images(self, imgs):
        self.images = json.dumps(imgs)

    def get_amenities(self):
        try:
            return json.loads(self.amenities or '[]')
        except Exception:
            return []

    def current_price(self, check_in=None):
        base = float(self.price_weekday or 0)
        if check_in:
            if isinstance(check_in, str):
                try:
                    check_in = datetime.strptime(check_in, '%Y-%m-%d').date()
                except Exception:
                    check_in = None
            if check_in and check_in.weekday() >= 5:
                weekend = float(self.price_weekend or 0)
                base = weekend if weekend > 0 else base
        if self.discount_percent:
            base = base * (1 - float(self.discount_percent) / 100)
        return round(max(base, 0), 2)


class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    booking_ref = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    check_in = db.Column(db.Date, nullable=False)
    check_out = db.Column(db.Date, nullable=False)
    guests = db.Column(db.Integer, default=1)
    total_amount = db.Column(db.Float, default=0)
    advance_paid = db.Column(db.Float, default=0)
    payment_status = db.Column(db.String(30), default='pending')
    booking_status = db.Column(db.String(30), default='pending')
    payment_method = db.Column(db.String(50))
    transaction_id = db.Column(db.String(100))
    special_requests = db.Column(db.Text)
    coupon_code = db.Column(db.String(50))
    discount_amount = db.Column(db.Float, default=0)
    payment_proof = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def nights(self):
        return (self.check_out - self.check_in).days


class SeminarBooking(db.Model):
    __tablename__ = 'seminar_bookings'
    id = db.Column(db.Integer, primary_key=True)
    booking_ref = db.Column(db.String(20), unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    event_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(10))
    end_time = db.Column(db.String(10))
    hours = db.Column(db.Float, default=1)
    capacity_needed = db.Column(db.Integer, default=50)
    rate_type = db.Column(db.String(20), default='hourly')
    total_amount = db.Column(db.Float, default=0)
    advance_paid = db.Column(db.Float, default=0)
    payment_status = db.Column(db.String(30), default='pending')
    booking_status = db.Column(db.String(30), default='pending')
    payment_method = db.Column(db.String(50))
    transaction_id = db.Column(db.String(100))
    payment_proof = db.Column(db.Text)
    contact_name = db.Column(db.String(120))
    contact_phone = db.Column(db.String(20))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MenuItem(db.Model):
    __tablename__ = 'menu_items'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(80), default='Main Course')
    price = db.Column(db.Float, default=0)
    image = db.Column(db.String(255))
    is_available = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)



class GalleryImage(db.Model):
    __tablename__ = 'gallery'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150))
    image = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), default='general')
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, default=5)
    comment = db.Column(db.Text)
    image = db.Column(db.String(255))
    is_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Coupon(db.Model):
    __tablename__ = 'coupons'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), default='percent')
    discount_value = db.Column(db.Float, default=0)
    min_amount = db.Column(db.Float, default=0)
    max_uses = db.Column(db.Integer, default=0)
    used_count = db.Column(db.Integer, default=0)
    valid_from = db.Column(db.Date)
    valid_until = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)


class Slider(db.Model):
    __tablename__ = 'sliders'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    subtitle = db.Column(db.String(300))
    image = db.Column(db.String(255))
    button_text = db.Column(db.String(50))
    button_link = db.Column(db.String(255))
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


class Amenity(db.Model):
    __tablename__ = 'amenities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), default='bi-star')
    description = db.Column(db.Text)
    image = db.Column(db.String(255))
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'))
    amount = db.Column(db.Float, default=0)
    method = db.Column(db.String(50))
    transaction_id = db.Column(db.String(100))
    status = db.Column(db.String(30), default='pending')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

print("Models defined OK")

# ===================== HELPERS =====================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def get_setting(key, default=''):
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else default


def set_setting(key, value):
    s = Setting.query.filter_by(key=key).first()
    if s:
        s.value = value
        s.updated_at = datetime.utcnow()
    else:
        s = Setting(key=key, value=value)
        db.session.add(s)
    db.session.commit()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def save_upload(file, subfolder='general'):
    """Upload to Cloudinary when configured; else local disk. Returns full URL or relative path."""
    if not file or not getattr(file, 'filename', None) or not allowed_file(file.filename):
        return None
    # Always try Cloudinary first if enabled
    if CLOUDINARY_ENABLED:
        try:
            import cloudinary.uploader
            try:
                file.seek(0)
            except Exception:
                pass
            res = cloudinary.uploader.upload(
                file,
                folder=f'hotelgrand/{subfolder}',
                resource_type='image',
                overwrite=False,
            )
            url = res.get('secure_url') or res.get('url')
            if url:
                print('Cloudinary upload OK:', url[:80])
                return url
            print('Cloudinary upload returned no URL:', res)
        except Exception as e:
            print('Cloudinary upload FAILED:', type(e).__name__, e)
            try:
                file.seek(0)
            except Exception:
                pass
    # Local disk fallback (ephemeral on Render free)
    try:
        file.seek(0)
    except Exception:
        pass
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{secrets.token_hex(8)}.{ext}"
    folder = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    file.save(path)
    print('Saved to LOCAL disk (will be lost on restart):', path)
    return f"{subfolder}/{filename}"


def media_url(path):
    """Resolve image path for templates (Cloudinary URL or local /uploads/)."""
    if not path:
        return ''
    p = str(path)
    if p.startswith('http://') or p.startswith('https://') or p.startswith('data:'):
        return p
    return '/uploads/' + p.lstrip('/')


def absolute_media(path):
    """Absolute https URL for favicon / Open Graph (required by Google)."""
    u = media_url(path)
    if not u:
        return 'https://i.ibb.co/wFXnS6pg/Chat-GPT-Image-Aug-1-2026-03-35-30-AM.png'
    if u.startswith('http://') or u.startswith('https://') or u.startswith('data:'):
        return u
    # relative path -> absolute using request host when available
    try:
        base = (request.url_root or '').rstrip('/')
        if base:
            return base + (u if u.startswith('/') else '/' + u)
    except Exception:
        pass
    return 'https://hotelgrand.com.np' + (u if u.startswith('/') else '/' + u)


def save_upload_base64(file):
    """Store image as data-URL in DB (survives Render ephemeral disk)."""
    import base64
    if not file or not file.filename or not allowed_file(file.filename):
        return None
    ext = file.filename.rsplit('.', 1)[1].lower()
    mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else f'image/{ext}'
    raw = file.read()
    if not raw:
        return None
    # Limit ~2.5MB decoded to keep DB reasonable
    if len(raw) > 2_500_000:
        return None
    b64 = base64.b64encode(raw).decode('ascii')
    return f'data:{mime};base64,{b64}'



def download_image_url(url, subfolder='general', timeout=20):
    """Download image from URL and store via Cloudinary or local disk. Returns path/URL or None."""
    import urllib.request
    from io import BytesIO
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; HotelGrandGarden/1.0)',
            'Accept': 'image/*,*/*',
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            ctype = (resp.headers.get('Content-Type') or 'image/jpeg').split(';')[0].strip()
        if not data or len(data) < 500:
            return None
        ext = 'jpg'
        if 'png' in ctype:
            ext = 'png'
        elif 'webp' in ctype:
            ext = 'webp'
        filename = f"auto_{secrets.token_hex(6)}.{ext}"
        # Cloudinary
        if CLOUDINARY_ENABLED:
            try:
                import cloudinary.uploader
                res = cloudinary.uploader.upload(
                    BytesIO(data),
                    folder=f'hotelgrand/{subfolder}',
                    resource_type='image',
                    overwrite=False,
                    public_id=filename.rsplit('.', 1)[0],
                )
                url_out = res.get('secure_url') or res.get('url')
                if url_out:
                    return url_out
            except Exception as e:
                print('Cloudinary auto-upload failed:', e)
        # Local
        folder = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, filename)
        with open(path, 'wb') as f:
            f.write(data)
        return f"{subfolder}/{filename}"
    except Exception as e:
        print('download_image_url failed:', url, e)
        return None


def auto_image_for_keyword(keyword, subfolder='general'):
    """Fetch a related stock photo by keyword (LoremFlickr / Picsum fallback)."""
    import urllib.parse
    kw = (keyword or 'hotel').replace(' ', ',')
    sources = [
        f'https://loremflickr.com/800/600/{urllib.parse.quote(kw)}',
        f'https://picsum.photos/seed/{urllib.parse.quote(keyword or "hotel")}/800/600',
    ]
    for u in sources:
        p = download_image_url(u, subfolder=subfolder)
        if p:
            return p
    return None


ROOM_PHOTO_KEYWORDS = {
    'Presidential Suite': 'luxury,hotel,suite,bedroom',
    'Standard Triple': 'hotel,bedroom,triple,beds',
    'Family Room': 'hotel,family,room,bedroom',
    'Deluxe AC Family': 'hotel,deluxe,bedroom,ac',
    'Master Suite': 'hotel,master,suite,bedroom',
}

MENU_PHOTO_KEYWORDS = {
    'Chicken': 'chicken,food,curry',
    'Mutton': 'mutton,curry,food',
    'Fish': 'fish,food,grilled',
    'Veg': 'vegetarian,food,curry',
    'Rice': 'rice,biryani,food',
    'Naan': 'naan,bread,indian',
    'Beer': 'beer,drink,glass',
    'Soda': 'soda,drink,refreshing',
    'Coffee': 'coffee,cup',
    'Tea': 'tea,cup',
    'Salad': 'salad,fresh',
    'Soup': 'soup,bowl',
    'Momo': 'momos,dumplings,nepal',
    'Chowmein': 'noodles,chowmein',
    'Pizza': 'pizza,food',
    'Burger': 'burger,food',
}


def keyword_for_menu(name):
    n = (name or '').lower()
    for k, v in MENU_PHOTO_KEYWORDS.items():
        if k.lower() in n:
            return v
    return (name or 'food') + ',food,restaurant'



def run_five_star_package(update_existing=True):
    """Add / update amenities, menu, policies and settings for a 5-star experience."""
    summary = {'amenities_added': 0, 'amenities_updated': 0, 'menu_added': 0, 'settings': 0}

    # --- Luxury settings / copy ---
    luxury_settings = {
        'about_short': 'A refined 5-star family hotel in Urlabari offering luxury rooms, fine dining, seminar facilities and outdoor events — where comfort meets Nepali hospitality.',
        'seo_title': 'Hotel Grand Garden | 5-Star Luxury Stay in Urlabari, Morang',
        'seo_description': 'Book 5-star luxury rooms at Hotel Grand Garden, Urlabari. AC suites, fine dining, seminar hall, outdoor events, free parking. Call 9816374804.',
        'policies': (
            '• Check-in: 2:00 PM | Check-out: 12:00 PM\n'
            '• Early check-in / late check-out subject to availability\n'
            '• Advance payment required to confirm booking\n'
            '• Free cancellation up to 24 hours before check-in\n'
            '• Valid government ID required at check-in\n'
            '• 24/7 front desk & room service\n'
            '• Complimentary Wi-Fi and parking for all guests\n'
            '• Outside food may be restricted in restaurant areas'
        ),
        'parking_info': 'Complimentary valet-style free parking for all hotel guests',
        'checkin_time': '2:00 PM',
        'checkout_time': '12:00 PM',
        'footer_text': '© Hotel Grand Garden Family Restaurant and Bar — Luxury stay in Urlabari, Morang. All rights reserved.',
    }
    for k, v in luxury_settings.items():
        if update_existing or not get_setting(k):
            set_setting(k, v)
            summary['settings'] += 1

    # --- 5-star amenities ---
    star_amenities = [
        ('Free High-Speed Wi-Fi', 'bi-wifi', 'Complimentary high-speed internet in all rooms and public areas'),
        ('24/7 Room Service', 'bi-bell', 'Round-the-clock in-room dining'),
        ('Swimming Pool', 'bi-water', 'Refreshing pool for guests (seasonal / as available)'),
        ('Fitness Center', 'bi-heart-pulse', 'Basic gym equipment for guest use'),
        ('Spa & Wellness', 'bi-flower1', 'Relaxing spa treatments on request'),
        ('Fine Dining Restaurant', 'bi-cup-hot', 'Multi-cuisine restaurant & bar'),
        ('Conference / Seminar Hall', 'bi-people', 'Fully equipped hall for meetings and events'),
        ('Outdoor Event Lawn', 'bi-tree', 'Garden lawn for weddings and celebrations'),
        ('Free Parking', 'bi-p-circle', 'Secure complimentary parking'),
        ('Airport / City Pickup', 'bi-car-front', 'Pickup service on request'),
        ('Laundry Service', 'bi-shirt', 'Same-day laundry on request'),
        ('Power Backup', 'bi-lightning-charge', 'Uninterrupted power supply'),
        ('CCTV Security', 'bi-shield-check', '24/7 surveillance for your safety'),
        ('Concierge Desk', 'bi-person-badge', 'Local tips, bookings and guest assistance'),
        ('Family Friendly', 'bi-emoji-smile', 'Spacious family rooms and child-friendly service'),
        ('Bar & Lounge', 'bi-cup-straw', 'Evening drinks and lounge seating'),
        ('Garden Seating', 'bi-flower2', 'Outdoor seating in green surroundings'),
        ('Hot Water', 'bi-droplet', '24-hour hot water in all rooms'),
    ]
    existing_am = {a.name.lower(): a for a in Amenity.query.all()}
    for i, (name, icon, desc) in enumerate(star_amenities):
        key = name.lower()
        if key in existing_am:
            if update_existing:
                a = existing_am[key]
                a.icon = icon
                a.description = desc
                a.is_active = True
                a.sort_order = i
                summary['amenities_updated'] += 1
        else:
            db.session.add(Amenity(name=name, icon=icon, description=desc, is_active=True, sort_order=i))
            summary['amenities_added'] += 1
    db.session.commit()

    # --- 5-star style menu items (add if missing) ---
    star_menu = [
        ('Welcome Drink', 'Complimentary seasonal welcome drink for in-house guests', 'Beverages', 0),
        ('Fresh Lime Soda', 'Freshly squeezed lime with soda', 'Beverages', 80),
        ('Masala Tea', 'Traditional spiced Nepali tea', 'Beverages', 50),
        ('Filter Coffee', 'Hot filter coffee', 'Beverages', 80),
        ('Seasonal Fresh Juice', 'Orange / pineapple / mix', 'Beverages', 150),
        ('Local Beer', 'Chilled local beer', 'Bar', 350),
        ('Soft Drinks', 'Coke / Fanta / Sprite', 'Bar', 80),
        ('Club Sandwich', 'Grilled club sandwich with fries', 'Starters', 350),
        ('Chicken Wings', 'Crispy spiced chicken wings', 'Starters', 400),
        ('Veg Spring Rolls', 'Crispy vegetable rolls with dip', 'Starters', 280),
        ('Tomato Soup', 'Creamy tomato soup', 'Starters', 200),
        ('Chicken Biryani', 'Aromatic biryani with raita', 'Main Course', 450),
        ('Mutton Curry', 'Slow-cooked mutton curry', 'Main Course', 550),
        ('Butter Chicken', 'Creamy butter chicken', 'Main Course', 480),
        ('Paneer Butter Masala', 'Cottage cheese in rich gravy', 'Main Course', 420),
        ('Dal Makhani', 'Creamy black lentils', 'Main Course', 320),
        ('Steamed Rice', 'Fragrant steamed rice', 'Main Course', 150),
        ('Butter Naan', 'Soft butter naan', 'Main Course', 80),
        ('Chicken Chowmein', 'Wok-tossed noodles', 'Main Course', 280),
        ('Veg Fried Rice', 'Vegetable fried rice', 'Main Course', 250),
        ('Grilled Fish', 'Chef special grilled fish', 'Main Course', 600),
        ('Chocolate Brownie', 'Warm brownie with ice cream', 'Desserts', 250),
        ('Ice Cream', 'Assorted flavours', 'Desserts', 150),
        ('Fresh Fruit Platter', 'Seasonal cut fruits', 'Desserts', 200),
        ('Executive Thali', 'Complete meal thali', 'Thali', 450),
        ('Room Service Tray', 'In-room dining service charge may apply', 'Service', 50),
    ]
    existing_menu = {x.name.lower(): x for x in MenuItem.query.all()}
    for i, (name, desc, cat, price) in enumerate(star_menu):
        key = name.lower()
        if key in existing_menu:
            if update_existing:
                it = existing_menu[key]
                it.description = desc
                it.category = cat
                it.price = price
                it.is_available = True
                it.sort_order = i
        else:
            db.session.add(MenuItem(
                name=name, description=desc, category=cat, price=price,
                is_available=True, sort_order=i
            ))
            summary['menu_added'] += 1
    db.session.commit()

    # Room description polish for empty / short descriptions
    luxury_room_blurb = {
        'Presidential Suite': 'Our finest 5-star suite with premium furnishings, king bed, AC, lounge seating and exclusive amenities for a memorable stay.',
        'Standard Triple': 'Comfortable non-AC triple room with three single beds — ideal for friends or small groups seeking value and cleanliness.',
        'Family Room': 'Spacious family room with double and single bed configuration, perfect for families traveling together.',
        'Deluxe AC Family': 'Air-conditioned deluxe family room with refined interiors, double + single bedding and modern comforts.',
        'Master Suite': 'Spacious AC master suite with two master beds — designed for families or groups who value space and comfort.',
    }
    for room in Room.query.all():
        blurb = luxury_room_blurb.get(room.name)
        if blurb and (update_existing or not room.description or len(room.description) < 40):
            room.description = blurb
    db.session.commit()

    return summary


def run_auto_photos(targets=None):
    """Download and assign photos for rooms, menu, amenities missing images.
    targets: None or list of 'rooms','menu','amenities','seminar','outdoor','hero'
    Returns summary dict.
    """
    targets = targets or ['rooms', 'menu', 'amenities', 'seminar', 'outdoor']
    summary = {'rooms': 0, 'menu': 0, 'amenities': 0, 'settings': 0, 'errors': []}

    if 'rooms' in targets:
        for room in Room.query.order_by(Room.sort_order).all():
            if room.get_images():
                continue
            kw = ROOM_PHOTO_KEYWORDS.get(room.name) or f'hotel,room,{room.name}'
            path = auto_image_for_keyword(kw, 'rooms')
            if path:
                # apply to all rooms same class
                for r in Room.query.filter_by(name=room.name).all():
                    if not r.get_images():
                        r.set_images([path])
                        summary['rooms'] += 1
            else:
                summary['errors'].append(f'Room {room.number}')
        db.session.commit()

    if 'menu' in targets:
        for item in MenuItem.query.all():
            if item.image:
                continue
            kw = keyword_for_menu(item.name)
            path = auto_image_for_keyword(kw, 'menu')
            if path:
                item.image = path
                summary['menu'] += 1
            else:
                summary['errors'].append(f'Menu {item.name}')
        db.session.commit()

    if 'amenities' in targets:
        for am in Amenity.query.all():
            if am.image:
                continue
            path = auto_image_for_keyword(f'{am.name},hotel,amenity', 'amenities')
            if path:
                am.image = path
                summary['amenities'] += 1
        db.session.commit()

    if 'seminar' in targets and not get_setting('seminar_image'):
        path = auto_image_for_keyword('conference,hall,seminar', 'general')
        if path:
            set_setting('seminar_image', path)
            summary['settings'] += 1
    if 'outdoor' in targets and not get_setting('outdoor_image'):
        path = auto_image_for_keyword('garden,outdoor,event,lawn', 'general')
        if path:
            set_setting('outdoor_image', path)
            summary['settings'] += 1
    if 'hero' in targets:
        # only if still default empty-ish
        cur = get_setting('hero_image', '')
        if not cur or 'ibb.co' in cur:
            path = auto_image_for_keyword('hotel,building,exterior', 'general')
            if path:
                set_setting('hero_image', path)
                summary['settings'] += 1

    return summary


def generate_ref(prefix='BK'):
    return f"{prefix}{datetime.now().strftime('%y%m%d')}{secrets.token_hex(3).upper()}"


def normalize_phone(phone):
    """Keep digits only for matching (handles +977, spaces, dashes)."""
    if not phone:
        return ''
    digits = ''.join(c for c in str(phone) if c.isdigit())
    if digits.startswith('977') and len(digits) >= 12:
        digits = digits[3:]
    return digits


def find_user_by_login(identifier):
    """Find user by email OR phone number."""
    ident = (identifier or '').strip()
    if not ident:
        return None
    user = User.query.filter_by(email=ident.lower()).first()
    if user:
        return user
    want = normalize_phone(ident)
    if not want:
        return None
    user = User.query.filter_by(phone=ident).first()
    if user:
        return user
    for u in User.query.filter(User.phone.isnot(None)).all():
        if normalize_phone(u.phone) == want:
            return u
    return None


def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_hex(16)
    return session['_csrf']


def validate_csrf():
    token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
    if not token or token != session.get('_csrf'):
        abort(400, description='CSRF validation failed')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def is_room_available(room_id, check_in, check_out, exclude_booking_id=None):
    """Only confirmed/completed bookings block the room.
    Pending (awaiting payment verify) does not hard-block so rooms still show."""
    q = Booking.query.filter(
        Booking.room_id == room_id,
        Booking.booking_status.in_(['confirmed', 'completed']),
        Booking.check_in < check_out,
        Booking.check_out > check_in
    )
    if exclude_booking_id:
        q = q.filter(Booking.id != exclude_booking_id)
    return q.count() == 0


def calc_revenue():
    """Revenue only when confirmed/completed AND full payment (paid)."""
    try:
        room_rev = db.session.query(db.func.coalesce(db.func.sum(Booking.total_amount), 0)).filter(
            Booking.booking_status.in_(['confirmed', 'completed']),
            Booking.payment_status == 'paid'
        ).scalar() or 0
        sem_rev = db.session.query(db.func.coalesce(db.func.sum(SeminarBooking.total_amount), 0)).filter(
            SeminarBooking.booking_status.in_(['confirmed', 'completed']),
            SeminarBooking.payment_status == 'paid'
        ).scalar() or 0
        return float(room_rev) + float(sem_rev)
    except Exception as e:
        print('calc_revenue error:', e)
        return 0.0


def calc_advance_total():
    try:
        room_adv = db.session.query(db.func.coalesce(db.func.sum(Booking.advance_paid), 0)).scalar() or 0
        sem_rev = db.session.query(db.func.coalesce(db.func.sum(SeminarBooking.advance_paid), 0)).scalar() or 0
        return float(room_adv) + float(sem_rev)
    except Exception as e:
        print('calc_advance_total error:', e)
        return 0.0



def hotel_context():
    return {
        'media_url': media_url,
        'hotel_name': get_setting('hotel_name', Config.HOTEL_NAME),
        'hotel_phone': get_setting('hotel_phone', Config.HOTEL_PHONE),
        'hotel_location': get_setting('hotel_location', Config.HOTEL_LOCATION),
        'currency': get_setting('currency', Config.CURRENCY),
        'whatsapp': get_setting('whatsapp', Config.WHATSAPP_NUMBER),
        'email': get_setting('email', 'info@hotelgrandgarden.com'),
        'facebook': get_setting('facebook', ''),
        'instagram': get_setting('instagram', ''),
        'twitter': get_setting('twitter', ''),
        'tiktok': get_setting('tiktok', ''),
        'seminar_image': get_setting('seminar_image', ''),
        'outdoor_image': get_setting('outdoor_image', ''),
        'og_image': get_setting('og_image', 'https://i.ibb.co/wFXnS6pg/Chat-GPT-Image-Aug-1-2026-03-35-30-AM.png'),
        'about_short': get_setting('about_short', 'A luxury family hotel with restaurant and bar in Urlabari, Morang.'),
        'primary_color': get_setting('primary_color', '#1a5f4a'),
        'secondary_color': get_setting('secondary_color', '#c9a227'),
        'hero_image': get_setting('hero_image', 'https://i.ibb.co/Xrd5x9hr/Whats-App-Image-2026-07-25-at-8-48-22-PM.jpg'),
        'page_bg_image': get_setting('page_bg_image', ''),
        'rooms_bg_image': get_setting('rooms_bg_image', ''),
        'amenities_bg_image': get_setting('amenities_bg_image', ''),
        'restaurant_bg_image': get_setting('restaurant_bg_image', ''),
        'gallery_bg_image': get_setting('gallery_bg_image', ''),
        'contact_bg_image': get_setting('contact_bg_image', ''),
        'bg_brightness': int(get_setting('bg_brightness', '35') or 35),
        'bg_overlay': max(0.0, min(0.95, (100 - int(get_setting('bg_brightness', '35') or 35)) / 100.0)),

        'csrf_token': csrf_token(),
        'seminar_day_rate': float(get_setting('seminar_day_rate', '15000')),
        'seminar_hour_rate': float(get_setting('seminar_hour_rate', '2000')),
        'seminar_capacity': int(get_setting('seminar_capacity', '150')),
        'outdoor_capacity': int(get_setting('outdoor_capacity', '500')),
        'parking_info': get_setting('parking_info', 'Free parking available'),
        'checkin_time': get_setting('checkin_time', '12:00 PM'),
        'checkout_time': get_setting('checkout_time', '11:00 AM'),
        'seo_title': get_setting('seo_title', Config.HOTEL_NAME),
        'seo_description': get_setting('seo_description', 'Book luxury rooms at Hotel Grand Garden, Urlabari, Morang, Nepal.'),
        'policies': get_setting('policies', 'Check-in: 12 PM | Check-out: 11 AM | Advance payment required for confirmation.'),
        'footer_text': get_setting('footer_text', '© 2024 Hotel Grand Garden. All rights reserved.'),
    }


def seed_database():
    # Repair any rooms that have zero price (common after partial deploys)
    try:
        fixed = 0
        defaults_by_number = {
            '101': (5000, 5500), '102': (1800, 1500), '103': (1800, 1500),
            '104': (1800, 1500), '105': (1800, 1500), '106': (1800, 1500),
            '107': (1800, 1500), '108': (2500, 2250), '109': (2500, 2250),
            '110': (2500, 2250), '201': (2500, 2250), '202': (2000, 1850),
            '204': (2000, 1850), '205': (2000, 1850),
        }
        for room in Room.query.all():
            if (not room.price_weekday or room.price_weekday <= 0) and room.number in defaults_by_number:
                room.price_weekday, room.price_weekend = defaults_by_number[room.number]
                fixed += 1
        if fixed:
            db.session.commit()
            print(f'Repaired prices for {fixed} rooms')
    except Exception as e:
        print('Price repair note:', e)

    if User.query.filter_by(role='admin').first():
        return

    admin = User(name='Admin', email='admin@hotelgrandgarden.com', phone='9816374804', role='admin')
    admin.set_password('admin123')
    db.session.add(admin)

    defaults = {
        'hotel_name': Config.HOTEL_NAME,
        'hotel_phone': Config.HOTEL_PHONE,
        'hotel_location': Config.HOTEL_LOCATION,
        'currency': Config.CURRENCY,
        'whatsapp': Config.WHATSAPP_NUMBER,
        'email': 'info@hotelgrandgarden.com',
        'about_short': 'Experience luxury and comfort at Hotel Grand Garden Family Restaurant and Bar, nestled in the heart of Urlabari-5, Morang, Nepal.',
        'primary_color': '#1a5f4a',
        'secondary_color': '#c9a227',
        'seminar_day_rate': '15000',
        'seminar_hour_rate': '2000',
        'seminar_capacity': '150',
        'outdoor_capacity': '500',
        'parking_info': 'Free parking available for all guests',
        'checkin_time': '12:00 PM',
        'checkout_time': '11:00 AM',
        'seo_title': 'Hotel Grand Garden | Luxury Stay in Urlabari, Morang',
        'seo_description': 'Book rooms at Hotel Grand Garden. AC & Non-AC rooms, seminar hall, outdoor events. Call 9816374804.',
        'policies': '• Check-in: 12:00 PM\n• Check-out: 11:00 AM\n• Advance payment mandatory\n• Free cancellation up to 24 hours before check-in\n• Valid ID required at check-in',
        'footer_text': '© 2024 Hotel Grand Garden Family Restaurant and Bar. All rights reserved.',
        'facebook': '', 'instagram': '', 'twitter': '', 'tiktok': '', 'seminar_image': '', 'outdoor_image': '', 'og_image': 'https://i.ibb.co/wFXnS6pg/Chat-GPT-Image-Aug-1-2026-03-35-30-AM.png',
    }
    for k, v in defaults.items():
        db.session.add(Setting(key=k, value=v))

    rooms_data = [
        {'number': '101', 'name': 'Presidential Suite', 'room_type': 'AC', 'beds': '1 King Bed', 'max_guests': 2,
         'price_weekday': 5000, 'price_weekend': 5500, 'is_featured': True, 'sort_order': 1,
         'description': 'Our finest suite with premium furnishings, king bed, AC, and exclusive amenities.',
         'amenities': json.dumps(['AC', 'King Bed', 'TV', 'WiFi', 'Mini Bar', 'Private Balcony'])},
        {'number': '102', 'name': 'Standard Triple', 'room_type': 'Non AC', 'beds': '3 Single Beds', 'max_guests': 3,
         'price_weekday': 1800, 'price_weekend': 1500, 'sort_order': 2,
         'description': 'Comfortable non-AC room with three single beds.',
         'amenities': json.dumps(['3 Single Beds', 'WiFi', 'TV', 'Attached Bathroom'])},
        {'number': '103', 'name': 'Standard Triple', 'room_type': 'Non AC', 'beds': '3 Single Beds', 'max_guests': 3,
         'price_weekday': 1800, 'price_weekend': 1500, 'sort_order': 3,
         'description': 'Comfortable non-AC room with three single beds.',
         'amenities': json.dumps(['3 Single Beds', 'WiFi', 'TV', 'Attached Bathroom'])},
        {'number': '104', 'name': 'Family Room', 'room_type': 'Non AC', 'beds': '1 Double + 1 Single', 'max_guests': 3,
         'price_weekday': 1800, 'price_weekend': 1500, 'sort_order': 4,
         'description': 'Spacious non-AC family room with one double and one single bed.',
         'amenities': json.dumps(['Double Bed', 'Single Bed', 'WiFi', 'TV'])},
        {'number': '105', 'name': 'Family Room', 'room_type': 'Non AC', 'beds': '1 Double + 1 Single', 'max_guests': 3,
         'price_weekday': 1800, 'price_weekend': 1500, 'sort_order': 5,
         'description': 'Spacious non-AC family room with one double and one single bed.',
         'amenities': json.dumps(['Double Bed', 'Single Bed', 'WiFi', 'TV'])},
        {'number': '106', 'name': 'Family Room', 'room_type': 'Non AC', 'beds': '1 Double + 1 Single', 'max_guests': 3,
         'price_weekday': 1800, 'price_weekend': 1500, 'sort_order': 6,
         'description': 'Spacious non-AC family room with one double and one single bed.',
         'amenities': json.dumps(['Double Bed', 'Single Bed', 'WiFi', 'TV'])},
        {'number': '107', 'name': 'Family Room', 'room_type': 'Non AC', 'beds': '1 Double + 1 Single', 'max_guests': 3,
         'price_weekday': 1800, 'price_weekend': 1500, 'sort_order': 7,
         'description': 'Spacious non-AC family room with one double and one single bed.',
         'amenities': json.dumps(['Double Bed', 'Single Bed', 'WiFi', 'TV'])},
        {'number': '108', 'name': 'Deluxe AC Family', 'room_type': 'AC', 'beds': '1 Double + 1 Single', 'max_guests': 3,
         'price_weekday': 2500, 'price_weekend': 2250, 'sort_order': 8,
         'description': 'Air-conditioned family room with double and single bed.',
         'amenities': json.dumps(['AC', 'Double Bed', 'Single Bed', 'WiFi', 'TV'])},
        {'number': '109', 'name': 'Deluxe AC Family', 'room_type': 'AC', 'beds': '1 Double + 1 Single', 'max_guests': 3,
         'price_weekday': 2500, 'price_weekend': 2250, 'sort_order': 9,
         'description': 'Air-conditioned family room with double and single bed.',
         'amenities': json.dumps(['AC', 'Double Bed', 'Single Bed', 'WiFi', 'TV'])},
        {'number': '110', 'name': 'Deluxe AC Family', 'room_type': 'AC', 'beds': '1 Double + 1 Single', 'max_guests': 3,
         'price_weekday': 2500, 'price_weekend': 2250, 'sort_order': 10,
         'description': 'Air-conditioned family room with double and single bed.',
         'amenities': json.dumps(['AC', 'Double Bed', 'Single Bed', 'WiFi', 'TV'])},
        {'number': '201', 'name': 'Deluxe AC Family', 'room_type': 'AC', 'beds': '1 Double + 1 Single', 'max_guests': 3,
         'price_weekday': 2500, 'price_weekend': 2250, 'sort_order': 11,
         'description': 'Air-conditioned family room with double and single bed.',
         'amenities': json.dumps(['AC', 'Double Bed', 'Single Bed', 'WiFi', 'TV'])},
        {'number': '202', 'name': 'Master Suite', 'room_type': 'AC', 'beds': '2 Master Beds', 'max_guests': 4,
         'price_weekday': 2000, 'price_weekend': 1850, 'sort_order': 12,
         'description': 'Spacious AC suite with two master beds for families or groups of four.',
         'amenities': json.dumps(['AC', '2 Master Beds', 'WiFi', 'TV', 'Seating Area'])},
        {'number': '204', 'name': 'Master Suite', 'room_type': 'AC', 'beds': '2 Master Beds', 'max_guests': 4,
         'price_weekday': 2000, 'price_weekend': 1850, 'sort_order': 13,
         'description': 'Spacious AC suite with two master beds for families or groups of four.',
         'amenities': json.dumps(['AC', '2 Master Beds', 'WiFi', 'TV', 'Seating Area'])},
        {'number': '205', 'name': 'Master Suite', 'room_type': 'AC', 'beds': '2 Master Beds', 'max_guests': 4,
         'price_weekday': 2000, 'price_weekend': 1850, 'sort_order': 14,
         'description': 'Spacious AC suite with two master beds for families or groups of four.',
         'amenities': json.dumps(['AC', '2 Master Beds', 'WiFi', 'TV', 'Seating Area'])},
    ]
    for r in rooms_data:
        db.session.add(Room(**r, images='[]'))

    for i, (name, icon) in enumerate([
        ('Free WiFi', 'bi-wifi'), ('Free Parking', 'bi-p-circle'), ('Restaurant', 'bi-cup-hot'),
        ('Bar', 'bi-cup-straw'), ('AC Rooms', 'bi-snow'), ('Room Service', 'bi-bell'),
        ('Seminar Hall', 'bi-people'), ('Outdoor Events', 'bi-tree'), ('24/7 Front Desk', 'bi-clock'),
        ('Laundry', 'bi-basket'), ('TV', 'bi-tv'), ('Attached Bathroom', 'bi-droplet'),
    ]):
        db.session.add(Amenity(name=name, icon=icon, sort_order=i, is_active=True))

    menu_items = [
        ('Chicken Momo', 'Steamed dumplings with spicy chutney', 'Appetizers', 250),
        ('Veg Chowmein', 'Stir-fried noodles with vegetables', 'Main Course', 180),
        ('Chicken Biryani', 'Aromatic rice with tender chicken', 'Main Course', 350),
        ('Thukpa', 'Himalayan noodle soup', 'Soup', 200),
        ('Dal Bhat Tarkari', 'Traditional Nepali set meal', 'Main Course', 300),
        ('Grilled Fish', 'Fresh local fish with herbs', 'Main Course', 450),
        ('Chocolate Brownie', 'Warm brownie with ice cream', 'Dessert', 220),
        ('Fresh Lime Soda', 'Refreshing lime drink', 'Beverages', 80),
        ('Local Beer', 'Chilled Nepali beer', 'Bar', 350),
        ('Club Sandwich', 'Triple-decker with fries', 'Snacks', 280),
    ]
    for i, (name, desc, cat, price) in enumerate(menu_items):
        db.session.add(MenuItem(name=name, description=desc, category=cat, price=price, sort_order=i, is_available=True))

    for name, rating, comment in [
        ('Ramesh K.', 5, 'Excellent stay! Clean rooms and friendly staff. The restaurant food is delicious.'),
        ('Sita T.', 5, 'Perfect for family. Spacious rooms and great location in Urlabari.'),
        ('Anil S.', 4, 'Good value for money. Seminar hall is well equipped. Will visit again.'),
    ]:
        db.session.add(Review(name=name, rating=rating, comment=comment, is_approved=True))

    db.session.add(Slider(title='Luxury Stay in Urlabari', subtitle='Experience comfort at Hotel Grand Garden',
                          button_text='Book Now', button_link='#rooms', sort_order=1, is_active=True))
    db.session.add(Slider(title='Restaurant & Bar', subtitle='Authentic flavors and refreshing drinks',
                          button_text='View Menu', button_link='#restaurant', sort_order=2, is_active=True))
    db.session.add(Slider(title='Events & Seminars', subtitle='Hall for 150 · Outdoor for 500',
                          button_text='Enquire Now', button_link='#seminar', sort_order=3, is_active=True))

    db.session.add(Coupon(code='WELCOME10', discount_type='percent', discount_value=10,
                          min_amount=2000, max_uses=100, is_active=True,
                          valid_from=date.today(), valid_until=date.today() + timedelta(days=365)))

    db.session.commit()
    print('Database seeded successfully.')

print("Helpers OK")

# ===================== PUBLIC ROUTES =====================

@app.route('/')
def index():
    rooms = Room.query.filter_by(is_available=True).order_by(Room.sort_order).all()
    amenities = Amenity.query.filter_by(is_active=True).order_by(Amenity.sort_order).all()
    menu = MenuItem.query.filter_by(is_available=True).order_by(MenuItem.sort_order).all()
    gallery = GalleryImage.query.order_by(GalleryImage.sort_order).limit(12).all()
    reviews = Review.query.filter_by(is_approved=True).order_by(Review.created_at.desc()).limit(6).all()
    sliders = Slider.query.filter_by(is_active=True).order_by(Slider.sort_order).all()
    ctx = hotel_context()
    return render_template_string(INDEX_HTML, rooms=rooms, amenities=amenities, menu=menu,
                                  gallery=gallery, reviews=reviews, sliders=sliders, **ctx)





@app.route('/admin/proof/booking/<int:booking_id>')
@admin_required
def view_booking_proof(booking_id):
    from flask import Response
    b = db.session.get(Booking, booking_id)
    if not b or not b.payment_proof:
        abort(404)
    proof = b.payment_proof
    if proof.startswith('data:'):
        try:
            header, b64 = proof.split(',', 1)
            mime = header.split(';')[0].replace('data:', '') or 'image/jpeg'
            import base64
            return Response(base64.b64decode(b64), mimetype=mime)
        except Exception:
            abort(404)
    if proof.startswith('http://') or proof.startswith('https://'):
        return redirect(proof)
    return redirect('/uploads/' + proof.lstrip('/'))


@app.route('/admin/proof/seminar/<int:seminar_id>')
@admin_required
def view_seminar_proof(seminar_id):
    from flask import Response
    s = db.session.get(SeminarBooking, seminar_id)
    if not s or not s.payment_proof:
        abort(404)
    proof = s.payment_proof
    if proof.startswith('data:'):
        try:
            header, b64 = proof.split(',', 1)
            mime = header.split(';')[0].replace('data:', '') or 'image/jpeg'
            import base64
            return Response(base64.b64decode(b64), mimetype=mime)
        except Exception:
            abort(404)
    if proof.startswith('http://') or proof.startswith('https://'):
        return redirect(proof)
    return redirect('/uploads/' + proof.lstrip('/'))



@app.route('/favicon.ico')
def favicon():
    """Google & browsers request /favicon.ico — serve hotel logo image."""
    try:
        icon = get_setting('og_image', '') or 'https://i.ibb.co/wFXnS6pg/Chat-GPT-Image-Aug-1-2026-03-35-30-AM.png'
        url = absolute_media(icon)
    except Exception:
        url = 'https://i.ibb.co/wFXnS6pg/Chat-GPT-Image-Aug-1-2026-03-35-30-AM.png'
    return redirect(url, code=302)


@app.route('/uploads/<path:filename>')
@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        validate_csrf()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('index') + '#authModal')
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('index') + '#authModal')
        user = User(name=name, email=email, phone=phone, role='customer')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Registration successful!', 'success')
        next_url = session.pop('next_after_login', None) or url_for('index')
        return redirect(next_url)
    return redirect(url_for('index') + '#authModal')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('index'))
    if request.method == 'POST':
        validate_csrf()
        identifier = (request.form.get('login') or request.form.get('email') or '').strip()
        password = request.form.get('password', '')
        user = find_user_by_login(identifier)
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=True)
            flash(f'Welcome back, {user.name}!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            next_url = session.pop('next_after_login', None) or url_for('index')
            return redirect(next_url)
        flash('Invalid email/phone or password.', 'danger')
    return redirect(url_for('index') + '#authModal')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))



@app.route('/api/available-rooms', methods=['GET', 'POST'])
def available_rooms():
    """Return available room numbers for a room class (by name) and dates."""
    try:
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
        else:
            data = request.args.to_dict() or {}
        class_name = (data.get('class_name') or '').strip()
        check_in = data.get('check_in')
        check_out = data.get('check_out')
        try:
            ci = datetime.strptime(str(check_in), '%Y-%m-%d').date()
            co = datetime.strptime(str(check_out), '%Y-%m-%d').date()
        except Exception:
            return jsonify({'rooms': [], 'error': 'Invalid dates'}), 400
        if co <= ci:
            return jsonify({'rooms': [], 'error': 'Check-out must be after check-in'}), 400
        q = Room.query.filter_by(is_available=True)
        if class_name:
            q = q.filter(Room.name == class_name)
        rooms = q.order_by(Room.number).all()
        # Fallback: if name filter yields nothing, try case-insensitive / strip
        if not rooms and class_name:
            all_rooms = Room.query.filter_by(is_available=True).order_by(Room.number).all()
            rooms = [r for r in all_rooms if (r.name or '').strip().lower() == class_name.lower()]
        result = []
        nights = (co - ci).days
        for room in rooms:
            try:
                avail = is_room_available(room.id, ci, co)
            except Exception as e:
                print('is_room_available error', room.id, e)
                avail = True
            if not avail:
                continue
            price = room.current_price(ci)
            result.append({
                'id': room.id,
                'number': room.number,
                'name': room.name,
                'room_type': room.room_type or '',
                'beds': room.beds or '',
                'max_guests': room.max_guests or 2,
                'price_per_night': float(price),
                'total': round(float(price) * nights, 2),
                'nights': nights,
            })
        return jsonify({
            'rooms': result,
            'currency': get_setting('currency', 'Rs'),
            'class_name': class_name,
            'count': len(result),
        })
    except Exception as e:
        print('available_rooms error:', e)
        return jsonify({'rooms': [], 'error': str(e)}), 500


@app.route('/api/check-availability', methods=['POST'])
def check_availability():
    data = request.get_json() or {}
    room_id = data.get('room_id')
    check_in = data.get('check_in')
    check_out = data.get('check_out')
    try:
        ci = datetime.strptime(check_in, '%Y-%m-%d').date()
        co = datetime.strptime(check_out, '%Y-%m-%d').date()
    except Exception:
        return jsonify({'available': False, 'error': 'Invalid dates'}), 400
    if co <= ci:
        return jsonify({'available': False, 'error': 'Check-out must be after check-in'}), 400
    room = db.session.get(Room, room_id)
    if not room:
        return jsonify({'available': False, 'error': 'Room not found'}), 404
    avail = is_room_available(room_id, ci, co)
    nights = (co - ci).days
    price_per_night = room.current_price(ci)
    total = price_per_night * nights
    return jsonify({
        'available': avail, 'nights': nights,
        'price_per_night': price_per_night, 'total': total,
        'currency': get_setting('currency', 'Rs')
    })


@app.route('/api/apply-coupon', methods=['POST'])
def apply_coupon():
    data = request.get_json() or {}
    code = (data.get('code') or '').strip().upper()
    amount = float(data.get('amount') or 0)
    coupon = Coupon.query.filter_by(code=code, is_active=True).first()
    if not coupon:
        return jsonify({'valid': False, 'message': 'Invalid coupon'})
    today = date.today()
    if coupon.valid_from and today < coupon.valid_from:
        return jsonify({'valid': False, 'message': 'Coupon not yet valid'})
    if coupon.valid_until and today > coupon.valid_until:
        return jsonify({'valid': False, 'message': 'Coupon expired'})
    if coupon.max_uses and coupon.used_count >= coupon.max_uses:
        return jsonify({'valid': False, 'message': 'Coupon usage limit reached'})
    if amount < coupon.min_amount:
        return jsonify({'valid': False, 'message': f'Minimum amount Rs {coupon.min_amount}'})
    if coupon.discount_type == 'percent':
        discount = round(amount * coupon.discount_value / 100, 2)
    else:
        discount = min(coupon.discount_value, amount)
    return jsonify({'valid': True, 'discount': discount, 'code': code})


@app.route('/book', methods=['POST'])
def book_room():
    validate_csrf()
    if not current_user.is_authenticated:
        session['pending_booking'] = request.form.to_dict()
        session['next_after_login'] = url_for('index') + '#rooms'
        flash('Please login or register to complete your booking.', 'warning')
        return redirect(url_for('index') + '#authModal')

    room_id = request.form.get('room_id')
    check_in = request.form.get('check_in')
    check_out = request.form.get('check_out')
    guests = int(request.form.get('guests') or 1)
    special = request.form.get('special_requests', '')
    coupon_code = request.form.get('coupon_code', '').strip().upper()
    payment_method = request.form.get('payment_method', 'esewa')
    advance = float(request.form.get('advance_amount') or 0)

    if not room_id:
        flash('Please select a room number.', 'danger')
        return redirect(url_for('index') + '#rooms')

    try:
        ci = datetime.strptime(check_in, '%Y-%m-%d').date()
        co = datetime.strptime(check_out, '%Y-%m-%d').date()
    except Exception:
        flash('Invalid dates.', 'danger')
        return redirect(url_for('index') + '#rooms')

    try:
        room = db.session.get(Room, int(room_id))
    except Exception:
        room = None
    if not room or not is_room_available(room.id, ci, co):
        flash('Room not available for selected dates.', 'danger')
        return redirect(url_for('index') + '#rooms')

    nights = (co - ci).days
    if nights < 1:
        flash('Minimum 1 night stay required.', 'danger')
        return redirect(url_for('index') + '#rooms')

    price_per = room.current_price(ci)
    total = price_per * nights
    discount = 0
    if coupon_code:
        coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
        if coupon:
            if coupon.discount_type == 'percent':
                discount = round(total * coupon.discount_value / 100, 2)
            else:
                discount = min(coupon.discount_value, total)
            coupon.used_count += 1
            total -= discount

    if advance <= 0:
        flash('Advance payment is mandatory.', 'danger')
        return redirect(url_for('index') + '#rooms')
    if advance > total:
        advance = total

    # Online payment requires payment proof screenshot
    allowed_methods = ('esewa', 'khalti', 'bank')
    if payment_method not in allowed_methods:
        flash('Please select eSewa, Khalti or Bank Transfer and upload payment proof.', 'danger')
        return redirect(url_for('index') + '#rooms')
    payment_proof = None
    if 'payment_proof' not in request.files or not request.files['payment_proof'].filename:
        flash('Payment proof screenshot is required. Pay advance and upload statement.', 'danger')
        return redirect(url_for('index') + '#rooms')
    f = request.files['payment_proof']
    payment_proof = save_upload(f, 'payments')
    if not payment_proof:
        try:
            f.seek(0)
        except Exception:
            pass
        payment_proof = save_upload_base64(f)
    if not payment_proof:
        flash('Invalid payment proof image. Use JPG/PNG.', 'danger')
        return redirect(url_for('index') + '#rooms')

    # Always require advance + proof; admin verifies before confirm
    pay_status = 'pending'
    book_status = 'pending'
    flash_msg = 'Booking submitted! Ref: {ref}. Waiting for admin to verify payment proof.'

    booking = Booking(
        booking_ref=generate_ref('BK'), user_id=current_user.id, room_id=room.id,
        check_in=ci, check_out=co, guests=guests, total_amount=total, advance_paid=advance,
        payment_status=pay_status, booking_status=book_status, payment_method=payment_method,
        transaction_id=request.form.get('transaction_id', ''),
        special_requests=special, coupon_code=coupon_code or None, discount_amount=discount,
        payment_proof=payment_proof
    )
    db.session.add(booking)
    db.session.flush()
    db.session.add(Payment(booking_id=booking.id, amount=advance, method=payment_method,
                           transaction_id=request.form.get('transaction_id', ''),
                           status='completed' if book_status == 'confirmed' else 'pending',
                           notes=f'Proof: {payment_proof}' if payment_proof else ''))
    db.session.commit()
    flash(flash_msg.format(ref=booking.booking_ref), 'success' if book_status == 'confirmed' else 'info')
    return redirect(url_for('my_bookings'))


@app.route('/my-bookings')
@login_required
def my_bookings():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc()).all()
    ctx = hotel_context()
    return render_template_string(INDEX_HTML, rooms=[], amenities=[], menu=[], gallery=[],
                                  reviews=[], sliders=[], my_bookings=bookings, show_my_bookings=True, **ctx)


@app.route('/book-seminar', methods=['POST'])
def book_seminar():
    validate_csrf()
    if not current_user.is_authenticated:
        flash('Please login to book the seminar hall.', 'warning')
        return redirect(url_for('index') + '#authModal')
    event_date = request.form.get('event_date')
    hours = float(request.form.get('hours') or 1)
    rate_type = request.form.get('rate_type', 'hourly')
    capacity = int(request.form.get('capacity') or 50)
    name = request.form.get('contact_name', current_user.name)
    phone = request.form.get('contact_phone', current_user.phone or '')
    notes = request.form.get('notes', '')
    advance = float(request.form.get('advance_amount') or 0)
    payment_method = request.form.get('payment_method', 'esewa')
    try:
        ed = datetime.strptime(event_date, '%Y-%m-%d').date()
    except Exception:
        flash('Invalid date.', 'danger')
        return redirect(url_for('index') + '#seminar')
    day_rate = float(get_setting('seminar_day_rate', '15000'))
    hour_rate = float(get_setting('seminar_hour_rate', '2000'))
    total = day_rate if rate_type == 'daily' else hour_rate * hours
    if advance <= 0:
        flash('Advance payment is mandatory.', 'danger')
        return redirect(url_for('index') + '#seminar')
    if advance > total:
        advance = total
    allowed_methods = ('esewa', 'khalti', 'bank')
    if payment_method not in allowed_methods:
        flash('Please select eSewa, Khalti or Bank Transfer and upload payment proof.', 'danger')
        return redirect(url_for('index') + '#seminar')
    payment_proof = None
    if 'payment_proof' not in request.files or not request.files['payment_proof'].filename:
        flash('Payment proof screenshot is required. Pay advance and upload statement.', 'danger')
        return redirect(url_for('index') + '#seminar')
    f = request.files['payment_proof']
    payment_proof = save_upload(f, 'payments')
    if not payment_proof:
        try:
            f.seek(0)
        except Exception:
            pass
        payment_proof = save_upload_base64(f)
    if not payment_proof:
        flash('Invalid payment proof. Use JPG/PNG.', 'danger')
        return redirect(url_for('index') + '#seminar')
    pay_status = 'pending'
    sb = SeminarBooking(
        booking_ref=generate_ref('SM'), user_id=current_user.id, event_date=ed,
        hours=hours, capacity_needed=capacity, rate_type=rate_type, total_amount=total,
        advance_paid=advance, payment_status=pay_status, booking_status='pending',
        payment_method=payment_method,
        transaction_id=request.form.get('transaction_id', ''),
        payment_proof=payment_proof,
        contact_name=name, contact_phone=phone, notes=notes
    )
    db.session.add(sb)
    db.session.commit()
    flash(f'Seminar hall request submitted! Ref: {sb.booking_ref}. Waiting for admin confirmation.', 'info')
    return redirect(url_for('index'))

@app.route('/submit-review', methods=['POST'])
def submit_review():
    validate_csrf()
    name = request.form.get('name', '').strip()
    rating = int(request.form.get('rating') or 5)
    comment = request.form.get('comment', '').strip()
    if not name or not comment:
        flash('Name and comment required.', 'danger')
        return redirect(url_for('index') + '#reviews')
    img = None
    if 'image' in request.files:
        img = save_upload(request.files['image'], 'reviews')
    db.session.add(Review(name=name, rating=min(5, max(1, rating)), comment=comment, image=img, is_approved=False))
    db.session.commit()
    flash('Thank you! Your review will appear after approval.', 'success')
    return redirect(url_for('index') + '#reviews')

print("Public routes OK")

# ===================== ADMIN ROUTES =====================


@app.route('/admin/cloudinary-status')
@admin_required
def cloudinary_status():
    info = {
        'enabled': CLOUDINARY_ENABLED,
        'CLOUDINARY_URL_set': bool(os.environ.get('CLOUDINARY_URL')),
        'CLOUDINARY_CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME') or os.environ.get('CLOUDINARY_CLOUD') or '',
        'CLOUDINARY_API_KEY_set': bool(os.environ.get('CLOUDINARY_API_KEY')),
        'CLOUDINARY_API_SECRET_set': bool(os.environ.get('CLOUDINARY_API_SECRET')),
    }
    if CLOUDINARY_ENABLED:
        try:
            import cloudinary.api
            # light ping — list root folders may need permission; just report config
            conf = cloudinary.config()
            info['cloud_name'] = getattr(conf, 'cloud_name', None)
            info['status'] = 'OK — new uploads go to Cloudinary and survive restart'
        except Exception as e:
            info['status'] = f'Enabled but error: {e}'
    else:
        info['status'] = 'DISABLED — uploads go to local disk and are LOST on restart'
    return jsonify(info)

@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = {
        'rooms': Room.query.count(),
        'bookings': Booking.query.count(),
        'customers': User.query.filter_by(role='customer').count(),
        'revenue': calc_revenue(), 'advance_total': calc_advance_total(),
        'pending': Booking.query.filter_by(booking_status='pending').count(),
        'confirmed': Booking.query.filter_by(booking_status='confirmed').count(),
    }
    recent = Booking.query.order_by(Booking.created_at.desc()).limit(8).all()
    ctx = hotel_context()
    return render_template_string(ADMIN_HTML, section='dashboard', stats=stats, recent=recent, data={}, **ctx)


@app.route('/admin/<section>', methods=['GET', 'POST'])
@admin_required
def admin_section(section):
    ctx = hotel_context()
    allowed = [
        'dashboard', 'hotel', 'rooms', 'bookings', 'customers', 'payments',
        'menu', 'gallery', 'reviews', 'amenities', 'sliders', 'coupons',
        'seminar', 'reports', 'seo', 'theme', 'backup', 'settings'
    ]
    if section not in allowed:
        abort(404)

    if request.method == 'POST':
        validate_csrf()
        action = request.form.get('action', '')

        if section in ('hotel', 'settings'):
            for key in request.form:
                if key not in ('action', 'csrf_token'):
                    set_setting(key, request.form[key])
            if 'logo' in request.files and request.files['logo'].filename:
                path = save_upload(request.files['logo'], 'general')
                if path:
                    set_setting('logo', path)
            flash('Settings saved.', 'success')
            return redirect(url_for('admin_section', section=section))

        if section == 'rooms':
            if action == 'five_star_package':
                summary = run_five_star_package(update_existing=True)
                flash(
                    f"5-star package applied — settings: {summary['settings']}, "
                    f"amenities +{summary['amenities_added']} / updated {summary['amenities_updated']}, "
                    f"menu +{summary['menu_added']}.",
                    'success'
                )
                return redirect(url_for('admin_section', section='rooms'))
            if action == 'auto_photos':
                targets = request.form.getlist('auto_targets') or ['rooms', 'menu', 'amenities', 'seminar', 'outdoor']
                summary = run_auto_photos(targets)
                flash(
                    f"Auto photos done — rooms: {summary['rooms']}, menu: {summary['menu']}, "
                    f"amenities: {summary['amenities']}, other: {summary['settings']}. "
                    f"Failed: {len(summary['errors'])}",
                    'success'
                )
                return redirect(url_for('admin_section', section='rooms'))
            if action == 'save_room':
                rid = request.form.get('room_id')
                room = db.session.get(Room, int(rid)) if rid else Room()
                room.number = request.form.get('number', room.number if rid else '')
                room.name = request.form.get('name', '')
                room.description = request.form.get('description', '')
                room.room_type = request.form.get('room_type', 'Non AC')
                room.beds = request.form.get('beds', '')
                room.max_guests = int(request.form.get('max_guests') or 2)
                room.price_weekday = float(request.form.get('price_weekday') or 0)
                room.price_weekend = float(request.form.get('price_weekend') or 0)
                room.discount_percent = float(request.form.get('discount_percent') or 0)
                room.is_available = request.form.get('is_available') == 'on'
                room.is_featured = request.form.get('is_featured') == 'on'
                room.sort_order = int(request.form.get('sort_order') or 0)
                am = request.form.get('amenities', '')
                room.amenities = json.dumps([a.strip() for a in am.split(',') if a.strip()])
                existing = room.get_images() if rid else []
                if 'images' in request.files:
                    for f in request.files.getlist('images'):
                        if f.filename:
                            p = save_upload(f, 'rooms')
                            if p:
                                existing.append(p)
                remove = request.form.getlist('remove_image')
                existing = [i for i in existing if i not in remove]
                room.set_images(existing)
                if not rid:
                    db.session.add(room)
                db.session.flush()
                # Apply photos to entire room class (same name)
                apply_class = request.form.get('apply_class_images') == 'on' or bool(
                    request.files.getlist('images') and any(f.filename for f in request.files.getlist('images'))
                )
                # Default: always sync class images when images changed or checkbox on
                if apply_class or request.form.get('apply_class_images') == 'on':
                    for other in Room.query.filter(Room.name == room.name, Room.id != room.id).all():
                        other.set_images(existing)
                db.session.commit()
                flash('Room saved. Class photos updated for all rooms named "{}".'.format(room.name), 'success')
            elif action == 'save_class_images':
                class_name = request.form.get('class_name', '').strip()
                if not class_name:
                    flash('Class name required.', 'danger')
                    return redirect(url_for('admin_section', section='rooms'))
                imgs = []
                # keep existing from first room of class unless replaced
                first = Room.query.filter_by(name=class_name).order_by(Room.sort_order).first()
                if first:
                    imgs = first.get_images()
                if 'images' in request.files:
                    for f in request.files.getlist('images'):
                        if f.filename:
                            p = save_upload(f, 'rooms')
                            if p:
                                imgs.append(p)
                remove = request.form.getlist('remove_image')
                imgs = [i for i in imgs if i not in remove]
                for r in Room.query.filter_by(name=class_name).all():
                    r.set_images(imgs)
                db.session.commit()
                flash(f'Class photo updated for "{class_name}".', 'success')
            elif action == 'delete_room':
                rid = request.form.get('room_id')
                room = db.session.get(Room, int(rid))
                if room:
                    db.session.delete(room)
                    db.session.commit()
                    flash('Room deleted.', 'info')
            return redirect(url_for('admin_section', section='rooms'))

        if section in ('bookings', 'payments'):
            if action == 'update_booking':
                bid = request.form.get('booking_id')
                b = db.session.get(Booking, int(bid))
                if b:
                    b.booking_status = request.form.get('booking_status', b.booking_status)
                    b.payment_status = request.form.get('payment_status', b.payment_status)
                    b.advance_paid = float(request.form.get('advance_paid') or b.advance_paid)
                    db.session.commit()
                    flash('Booking updated.', 'success')
            elif action == 'mark_full_payment':
                bid = request.form.get('booking_id')
                b = db.session.get(Booking, int(bid))
                if b:
                    b.payment_status = 'paid'
                    b.advance_paid = float(b.total_amount or 0)
                    # Must be confirmed/completed to count in revenue
                    if b.booking_status not in ('confirmed', 'completed'):
                        b.booking_status = 'confirmed'
                    try:
                        db.session.add(Payment(
                            booking_id=b.id, amount=float(b.total_amount or 0),
                            method=b.payment_method or 'cash', status='completed',
                            notes='Full payment recorded by admin'
                        ))
                    except Exception:
                        pass
                    db.session.commit()
                    flash(f'Full payment recorded for {b.booking_ref}. Counted in revenue.', 'success')
            elif action == 'record_advance':
                bid = request.form.get('booking_id')
                amount = float(request.form.get('advance_amount') or 0)
                b = db.session.get(Booking, int(bid))
                if b and amount > 0:
                    b.advance_paid = (b.advance_paid or 0) + amount
                    if b.advance_paid >= (b.total_amount or 0):
                        b.payment_status = 'paid'
                        b.advance_paid = b.total_amount
                    else:
                        b.payment_status = 'partial'
                    db.session.add(Payment(
                        booking_id=b.id, amount=amount,
                        method=request.form.get('payment_method') or b.payment_method or 'cash',
                        status='completed', notes='Advance recorded by admin'
                    ))
                    db.session.commit()
                    flash(f'Advance recorded for {b.booking_ref}.', 'success')
            elif action == 'delete_booking':
                bid = request.form.get('booking_id')
                b = db.session.get(Booking, int(bid))
                if b:
                    # Delete related payments first
                    Payment.query.filter_by(booking_id=b.id).delete()
                    db.session.delete(b)
                    db.session.commit()
                    flash('Booking deleted.', 'info')
            elif action == 'delete_all_bookings':
                Payment.query.delete()
                Booking.query.delete()
                db.session.commit()
                flash('All room bookings deleted.', 'info')
            elif action == 'update_seminar':
                sid = request.form.get('seminar_id')
                s = db.session.get(SeminarBooking, int(sid))
                if s:
                    s.booking_status = request.form.get('booking_status', s.booking_status)
                    s.payment_status = request.form.get('payment_status', s.payment_status)
                    if request.form.get('advance_paid') not in (None, ''):
                        s.advance_paid = float(request.form.get('advance_paid'))
                    db.session.commit()
                    flash('Seminar booking updated.', 'success')
            elif action == 'mark_seminar_full_payment':
                sid = request.form.get('seminar_id')
                s = db.session.get(SeminarBooking, int(sid))
                if s:
                    s.payment_status = 'paid'
                    s.advance_paid = float(s.total_amount or 0)
                    if s.booking_status not in ('confirmed', 'completed'):
                        s.booking_status = 'confirmed'
                    db.session.commit()
                    flash(f'Full payment recorded for {s.booking_ref}. Counted in revenue.', 'success')
            elif action == 'delete_seminar':
                sid = request.form.get('seminar_id')
                s = db.session.get(SeminarBooking, int(sid))
                if s:
                    db.session.delete(s)
                    db.session.commit()
                    flash('Seminar booking deleted.', 'info')
            elif action == 'delete_all_seminars':
                SeminarBooking.query.delete()
                db.session.commit()
                flash('All seminar bookings deleted.', 'info')
            return redirect(url_for('admin_section', section=section))

        if section == 'menu':
            if action == 'auto_photos':
                summary = run_auto_photos(['menu'])
                flash(f"Menu photos auto-filled: {summary['menu']}", 'success')
                return redirect(url_for('admin_section', section='menu'))
            if action == 'save_menu':
                mid = request.form.get('item_id')
                item = db.session.get(MenuItem, int(mid)) if mid else MenuItem()
                item.name = request.form.get('name', '')
                item.description = request.form.get('description', '')
                item.category = request.form.get('category', 'Main Course')
                item.price = float(request.form.get('price') or 0)
                item.is_available = request.form.get('is_available') == 'on'
                item.is_featured = request.form.get('is_featured') == 'on'
                item.sort_order = int(request.form.get('sort_order') or 0)
                if 'image' in request.files and request.files['image'].filename:
                    p = save_upload(request.files['image'], 'menu')
                    if p:
                        item.image = p
                if not mid:
                    db.session.add(item)
                db.session.commit()
                flash('Menu item saved.', 'success')
            elif action == 'delete_menu':
                mid = request.form.get('item_id')
                item = db.session.get(MenuItem, int(mid))
                if item:
                    db.session.delete(item)
                    db.session.commit()
                    flash('Item deleted.', 'info')
            return redirect(url_for('admin_section', section='menu'))

        if section == 'gallery':
            if action == 'add_gallery':
                files = request.files.getlist('images')
                title = request.form.get('title', '')
                cat = request.form.get('category', 'general')
                for f in files:
                    if f.filename:
                        p = save_upload(f, 'gallery')
                        if p:
                            db.session.add(GalleryImage(title=title, image=p, category=cat))
                db.session.commit()
                flash('Images uploaded.', 'success')
            elif action == 'delete_gallery':
                gid = request.form.get('image_id')
                g = db.session.get(GalleryImage, int(gid))
                if g:
                    db.session.delete(g)
                    db.session.commit()
                    flash('Image deleted.', 'info')
            return redirect(url_for('admin_section', section='gallery'))

        if section == 'reviews':
            if action == 'approve_review':
                rid = request.form.get('review_id')
                r = db.session.get(Review, int(rid))
                if r:
                    r.is_approved = True
                    db.session.commit()
                    flash('Review approved.', 'success')
            elif action == 'delete_review':
                rid = request.form.get('review_id')
                r = db.session.get(Review, int(rid))
                if r:
                    db.session.delete(r)
                    db.session.commit()
                    flash('Review deleted.', 'info')
            elif action == 'add_review':
                name = request.form.get('name', '')
                rating = int(request.form.get('rating') or 5)
                comment = request.form.get('comment', '')
                img = None
                if 'image' in request.files:
                    img = save_upload(request.files['image'], 'reviews')
                db.session.add(Review(name=name, rating=rating, comment=comment, image=img, is_approved=True))
                db.session.commit()
                flash('Review added.', 'success')
            return redirect(url_for('admin_section', section='reviews'))

        if section == 'amenities':
            if action == 'save_amenity':
                aid = request.form.get('amenity_id')
                a = db.session.get(Amenity, int(aid)) if aid else Amenity()
                a.name = request.form.get('name', '')
                a.icon = request.form.get('icon', 'bi-star')
                a.description = request.form.get('description', '')
                a.is_active = request.form.get('is_active') == 'on'
                a.sort_order = int(request.form.get('sort_order') or 0)
                if 'image' in request.files and request.files['image'].filename:
                    p = save_upload(request.files['image'], 'amenities')
                    if p:
                        a.image = p
                if not aid:
                    db.session.add(a)
                db.session.commit()
                flash('Amenity saved.', 'success')
            elif action == 'delete_amenity':
                aid = request.form.get('amenity_id')
                a = db.session.get(Amenity, int(aid))
                if a:
                    db.session.delete(a)
                    db.session.commit()
                    flash('Amenity deleted.', 'info')
            return redirect(url_for('admin_section', section='amenities'))

        if section == 'sliders':
            if action == 'save_slider':
                sid = request.form.get('slider_id')
                s = db.session.get(Slider, int(sid)) if sid else Slider()
                s.title = request.form.get('title', '')
                s.subtitle = request.form.get('subtitle', '')
                s.button_text = request.form.get('button_text', '')
                s.button_link = request.form.get('button_link', '')
                s.sort_order = int(request.form.get('sort_order') or 0)
                s.is_active = request.form.get('is_active') == 'on'
                if 'image' in request.files and request.files['image'].filename:
                    p = save_upload(request.files['image'], 'slider')
                    if p:
                        s.image = p
                if not sid:
                    db.session.add(s)
                db.session.commit()
                flash('Slider saved.', 'success')
            elif action == 'delete_slider':
                sid = request.form.get('slider_id')
                s = db.session.get(Slider, int(sid))
                if s:
                    db.session.delete(s)
                    db.session.commit()
                    flash('Slider deleted.', 'info')
            return redirect(url_for('admin_section', section='sliders'))

        if section == 'coupons':
            if action == 'save_coupon':
                cid = request.form.get('coupon_id')
                c = db.session.get(Coupon, int(cid)) if cid else Coupon()
                c.code = request.form.get('code', '').upper()
                c.discount_type = request.form.get('discount_type', 'percent')
                c.discount_value = float(request.form.get('discount_value') or 0)
                c.min_amount = float(request.form.get('min_amount') or 0)
                c.max_uses = int(request.form.get('max_uses') or 0)
                c.is_active = request.form.get('is_active') == 'on'
                vf = request.form.get('valid_from')
                vu = request.form.get('valid_until')
                c.valid_from = datetime.strptime(vf, '%Y-%m-%d').date() if vf else None
                c.valid_until = datetime.strptime(vu, '%Y-%m-%d').date() if vu else None
                if not cid:
                    db.session.add(c)
                db.session.commit()
                flash('Coupon saved.', 'success')
            elif action == 'delete_coupon':
                cid = request.form.get('coupon_id')
                c = db.session.get(Coupon, int(cid))
                if c:
                    db.session.delete(c)
                    db.session.commit()
                    flash('Coupon deleted.', 'info')
            return redirect(url_for('admin_section', section='coupons'))

        if section == 'customers':
            if action == 'toggle_user':
                uid = request.form.get('user_id')
                u = db.session.get(User, int(uid))
                if u and u.role != 'admin':
                    u.is_active = not u.is_active
                    db.session.commit()
                    flash('User status updated.', 'success')
            return redirect(url_for('admin_section', section='customers'))

        if section == 'theme':
            if request.form.get('primary_color'):
                set_setting('primary_color', request.form.get('primary_color', '#1a5f4a'))
            if request.form.get('secondary_color'):
                set_setting('secondary_color', request.form.get('secondary_color', '#c9a227'))
            # Background images
            bg_fields = [
                'hero_image', 'page_bg_image', 'rooms_bg_image',
                'amenities_bg_image', 'restaurant_bg_image',
                'gallery_bg_image', 'contact_bg_image',
            ]
            for field in bg_fields:
                if field in request.files and request.files[field].filename:
                    p = save_upload(request.files[field], 'general')
                    if p:
                        set_setting(field, p)
                # optional URL paste
                url_key = field + '_url'
                if request.form.get(url_key, '').strip():
                    set_setting(field, request.form.get(url_key).strip())
                if request.form.get('remove_' + field) == 'on':
                    if field == 'hero_image':
                        set_setting(field, 'https://i.ibb.co/Xrd5x9hr/Whats-App-Image-2026-07-25-at-8-48-22-PM.jpg')
                    else:
                        set_setting(field, '')
            br = request.form.get('bg_brightness')
            if br is not None and str(br).strip() != '':
                try:
                    br_i = max(0, min(100, int(float(br))))
                    set_setting('bg_brightness', str(br_i))
                except Exception:
                    pass
            flash('Theme & backgrounds saved. Refresh homepage to see changes.', 'success')
            return redirect(url_for('admin_section', section='theme'))


        if section == 'seo':
            set_setting('seo_title', request.form.get('seo_title', ''))
            set_setting('seo_description', request.form.get('seo_description', ''))
            if 'og_image' in request.files and request.files['og_image'].filename:
                p = save_upload(request.files['og_image'], 'general')
                if p:
                    set_setting('og_image', p)
            if request.form.get('og_image_url', '').strip():
                set_setting('og_image', request.form.get('og_image_url').strip())
            flash('SEO settings saved.', 'success')
            return redirect(url_for('admin_section', section='seo'))

        if section == 'seminar':
            set_setting('seminar_day_rate', request.form.get('seminar_day_rate', '15000'))
            set_setting('seminar_hour_rate', request.form.get('seminar_hour_rate', '2000'))
            set_setting('seminar_capacity', request.form.get('seminar_capacity', '150'))
            set_setting('outdoor_capacity', request.form.get('outdoor_capacity', '500'))
            if 'seminar_image' in request.files and request.files['seminar_image'].filename:
                p = save_upload(request.files['seminar_image'], 'general')
                if p:
                    set_setting('seminar_image', p)
            if 'outdoor_image' in request.files and request.files['outdoor_image'].filename:
                p = save_upload(request.files['outdoor_image'], 'general')
                if p:
                    set_setting('outdoor_image', p)
            if request.form.get('remove_seminar_image') == 'on':
                set_setting('seminar_image', '')
            if request.form.get('remove_outdoor_image') == 'on':
                set_setting('outdoor_image', '')
            flash('Seminar/Outdoor settings saved.', 'success')
            return redirect(url_for('admin_section', section='seminar'))

        if section == 'backup':
            if action == 'backup':
                data_export = {
                    'settings': {s.key: s.value for s in Setting.query.all()},
                    'rooms': [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in Room.query.all()],
                    'exported_at': datetime.utcnow().isoformat()
                }
                backup_path = os.path.join(app.config['UPLOAD_FOLDER'], 'backup.json')
                with open(backup_path, 'w') as f:
                    json.dump(data_export, f, default=str, indent=2)
                flash('Backup created at static/uploads/backup.json', 'success')
            return redirect(url_for('admin_section', section='backup'))

    # GET data
    data = {}
    if section == 'dashboard':
        data['stats'] = {
            'rooms': Room.query.count(),
            'bookings': Booking.query.count(),
            'customers': User.query.filter_by(role='customer').count(),
            'revenue': calc_revenue(), 'advance_total': calc_advance_total(),
            'pending': Booking.query.filter_by(booking_status='pending').count(),
            'confirmed': Booking.query.filter_by(booking_status='confirmed').count(),
        }
        data['recent'] = Booking.query.order_by(Booking.created_at.desc()).limit(10).all()
    elif section == 'rooms':
        data['rooms'] = Room.query.order_by(Room.sort_order).all()
        data['edit_room'] = None
        if request.args.get('edit'):
            data['edit_room'] = db.session.get(Room, int(request.args.get('edit')))
    elif section == 'bookings':
        data['bookings'] = Booking.query.order_by(Booking.created_at.desc()).all()
        data['seminar_bookings'] = SeminarBooking.query.order_by(SeminarBooking.created_at.desc()).all()
    elif section == 'customers':
        data['customers'] = User.query.filter_by(role='customer').order_by(User.created_at.desc()).all()
        # Map user_id -> list of bookings for detail view
        cb = {}
        for b in Booking.query.order_by(Booking.created_at.desc()).all():
            cb.setdefault(b.user_id, []).append(b)
        data['customer_bookings'] = cb
    elif section == 'payments':
        data['payments'] = Payment.query.order_by(Payment.created_at.desc()).all()
        data['bookings'] = Booking.query.order_by(Booking.created_at.desc()).all()
        data['seminar_bookings'] = SeminarBooking.query.order_by(SeminarBooking.created_at.desc()).all()
        data['advance_total'] = calc_advance_total()
        data['revenue'] = calc_revenue()
        data['awaiting_full'] = Booking.query.filter(
            Booking.payment_status.in_(['pending', 'partial'])
        ).count()
        data['paid_count'] = Booking.query.filter_by(payment_status='paid').count()
    elif section == 'menu':
        data['menu'] = MenuItem.query.order_by(MenuItem.sort_order).all()
        data['edit_item'] = None
        if request.args.get('edit'):
            data['edit_item'] = db.session.get(MenuItem, int(request.args.get('edit')))
    elif section == 'gallery':
        data['gallery'] = GalleryImage.query.order_by(GalleryImage.sort_order).all()
    elif section == 'reviews':
        data['reviews'] = Review.query.order_by(Review.created_at.desc()).all()
    elif section == 'amenities':
        data['amenities'] = Amenity.query.order_by(Amenity.sort_order).all()
        data['edit_amenity'] = None
        if request.args.get('edit'):
            data['edit_amenity'] = db.session.get(Amenity, int(request.args.get('edit')))
    elif section == 'sliders':
        data['sliders'] = Slider.query.order_by(Slider.sort_order).all()
        data['edit_slider'] = None
        if request.args.get('edit'):
            data['edit_slider'] = db.session.get(Slider, int(request.args.get('edit')))
    elif section == 'coupons':
        data['coupons'] = Coupon.query.order_by(Coupon.id.desc()).all()
        data['edit_coupon'] = None
        if request.args.get('edit'):
            data['edit_coupon'] = db.session.get(Coupon, int(request.args.get('edit')))
    elif section == 'reports':
        data['bookings'] = Booking.query.order_by(Booking.created_at.desc()).all()
        data['total_revenue'] = calc_revenue()
        data['advance_total'] = calc_advance_total()
        data['total_bookings'] = Booking.query.count()
        data['by_status'] = {
            'confirmed': Booking.query.filter_by(booking_status='confirmed').count(),
            'pending': Booking.query.filter_by(booking_status='pending').count(),
            'cancelled': Booking.query.filter_by(booking_status='cancelled').count(),
            'completed': Booking.query.filter_by(booking_status='completed').count(),
        }
    elif section in ('hotel', 'settings'):
        data['settings'] = {s.key: s.value for s in Setting.query.all()}

    return render_template_string(ADMIN_HTML, section=section, data=data, **ctx)

print("Admin routes OK")

# ===================== TEMPLATES & INIT =====================

def load_template(name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


app.jinja_env.globals['media_url'] = media_url
app.jinja_env.globals['absolute_media'] = absolute_media

def init_app():
    """Load templates + create DB tables. Safe to call multiple times."""
    global INDEX_HTML, ADMIN_HTML
    if INDEX_HTML is None:
        INDEX_HTML = load_template('index1.html')
    if ADMIN_HTML is None:
        ADMIN_HTML = load_template('admin1.html')
    # Ensure upload directories exist (needed on Render)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    for sub in ['rooms', 'gallery', 'slider', 'menu', 'amenities', 'general', 'reviews']:
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], sub), exist_ok=True)
    with app.app_context():
        db.create_all()
        # Add / widen payment_proof column (stores base64 data-URL)
        try:
            from sqlalchemy import text, inspect
            insp = inspect(db.engine)
            if 'bookings' in insp.get_table_names():
                cols = {c['name']: c for c in insp.get_columns('bookings')}
                if 'payment_proof' not in cols:
                    db.session.execute(text('ALTER TABLE bookings ADD COLUMN payment_proof TEXT'))
                    db.session.commit()
                    print('Added payment_proof TEXT column')
                else:
                    # Try widen to TEXT on Postgres
                    try:
                        db.session.execute(text('ALTER TABLE bookings ALTER COLUMN payment_proof TYPE TEXT'))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
        except Exception as e:
            print('Migration note:', e)
        try:
            from sqlalchemy import text, inspect
            insp = inspect(db.engine)
            if 'seminar_bookings' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('seminar_bookings')]
                for col, typ in [
                    ('payment_method', 'VARCHAR(50)'),
                    ('transaction_id', 'VARCHAR(100)'),
                    ('payment_proof', 'TEXT'),
                ]:
                    if col not in cols:
                        db.session.execute(text(f'ALTER TABLE seminar_bookings ADD COLUMN {col} {typ}'))
                        db.session.commit()
                        print(f'Added seminar_bookings.{col}')
        except Exception as e:
            print('Seminar migration note:', e)
        seed_database()


INDEX_HTML = None
ADMIN_HTML = None

@app.context_processor
def inject_globals():
    return {
        'get_setting': get_setting,
        'current_user': current_user,
    }


# Run init on import (needed for gunicorn / Render)
try:
    init_app()
except Exception as e:
    print('Init warning:', e)


if __name__ == '__main__':
    init_app()
    print('=' * 60)
    print('  Hotel Grand Garden – Management System')
    print('  http://127.0.0.1:5000')
    print('  Admin: admin@hotelgrandgarden.com / admin123')
    print('=' * 60)
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
