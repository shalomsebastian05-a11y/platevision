from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import uuid
import boto3
import pytesseract
from PIL import Image
import cv2
import numpy as np
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

app.secret_key = os.getenv('SECRET_KEY', 'mysecretkey123')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ── S3 ─────────────────────────────────────────────────────
s3 = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION', 'ap-south-1')
)
S3_BUCKET = os.getenv('S3_BUCKET_NAME')

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# ── Models ─────────────────────────────────────────────────
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class VehicleLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    plate_number = db.Column(db.String(20))
    image_s3_key = db.Column(db.String(255))
    entry_time = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()
    admin = User.query.filter_by(email='admin@plate.com').first()
    if not admin:
        hashed = bcrypt.generate_password_hash('admin123').decode('utf-8')
        admin = User(name='Admin', email='admin@plate.com',
                     password_hash=hashed, role='admin')
        db.session.add(admin)
        db.session.commit()

# ── Helpers ────────────────────────────────────────────────
def upload_to_s3(file_bytes, original_filename, content_type='image/jpeg'):
    ext = os.path.splitext(original_filename)[1].lower() or '.jpg'
    key = f"plates/{uuid.uuid4().hex}{ext}"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type
    )
    return key

def get_s3_url(key):
    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': S3_BUCKET, 'Key': key},
        ExpiresIn=3600
    )

def preprocess(file_bytes):
    np_arr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    if w < 600:
        scale = 600 / w
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    _, thresh = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

def run_ocr(file_bytes):
    img_array = preprocess(file_bytes)
    pil_img = Image.fromarray(img_array)
    config = r'--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    text = pytesseract.image_to_string(pil_img, config=config)
    plate = ''.join(e for e in text if e.isalnum()).upper().strip()
    print(f"[OCR RESULT]: {plate}")
    return plate if plate else 'UNREADABLE'

# ── Routes ─────────────────────────────────────────────────
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = bcrypt.generate_password_hash(
            request.form['password']).decode('utf-8')
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('Email already exists!', 'danger')
        else:
            user = User(name=name, email=email, password_hash=password)
            db.session.add(user)
            db.session.commit()
            flash('Registration successful!', 'success')
            return redirect(url_for('login'))
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        flash('Invalid email or password!', 'danger')
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    logs = VehicleLog.query.filter_by(user_id=session['user_id']).all()
    total_scans = len(logs)
    successful = len([l for l in logs if l.plate_number != 'UNREADABLE'])
    for log in logs:
        log.image_url = get_s3_url(log.image_s3_key) if log.image_s3_key else None
    return render_template('user/dashboard.html',
        logs=logs, total_scans=total_scans, successful=successful)

@app.route('/admin')
def admin_dashboard():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
    total_users = User.query.count()
    total_logs = VehicleLog.query.count()
    recent_logs = VehicleLog.query.order_by(
        VehicleLog.created_at.desc()).limit(10).all()
    for log in recent_logs:
        log.image_url = get_s3_url(log.image_s3_key) if log.image_s3_key else None
    return render_template('admin/dashboard.html',
        total_users=total_users, total_logs=total_logs, recent_logs=recent_logs)

@app.route('/upload', methods=['POST'])
def upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if 'plate_image' not in request.files:
        flash('No image uploaded!', 'danger')
        return redirect(url_for('dashboard'))
    file = request.files['plate_image']
    if file.filename == '':
        flash('No image selected!', 'danger')
        return redirect(url_for('dashboard'))

    file_bytes = file.read()

    # 1. OCR in memory
    plate_text = run_ocr(file_bytes)

    # 2. Upload to S3
    s3_key = upload_to_s3(file_bytes, file.filename,
                           file.content_type or 'image/jpeg')

    # 3. Save to RDS
    log = VehicleLog(
        user_id=session['user_id'],
        plate_number=plate_text,
        image_s3_key=s3_key
    )
    db.session.add(log)
    db.session.commit()

    flash(f'Plate detected: {plate_text}', 'success')
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
