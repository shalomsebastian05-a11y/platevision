from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

import os
import cv2
import pytesseract
import boto3

from datetime import datetime

# =========================
# LOAD ENV
# =========================

load_dotenv()

# =========================
# FLASK CONFIG
# =========================

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY')

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'uploads'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# =========================
# AWS S3 CONFIG
# =========================

S3_BUCKET = os.getenv('S3_BUCKET')

s3 = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY'),
    aws_secret_access_key=os.getenv('AWS_SECRET_KEY'),
    region_name='ap-south-1'
)

# =========================
# DATABASE MODELS
# =========================

class User(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(200),
        nullable=False
    )


class VehicleLog(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer)

    plate_number = db.Column(db.String(100))

    image_url = db.Column(db.String(500))

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

# =========================
# HOME
# =========================

@app.route('/')
def home():

    return redirect(url_for('login'))

# =========================
# REGISTER
# =========================

@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        username = request.form['username']

        password = request.form['password']

        existing_user = User.query.filter_by(
            username=username
        ).first()

        if existing_user:

            flash('Username already exists')

            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        new_user = User(
            username=username,
            password=hashed_password
        )

        db.session.add(new_user)

        db.session.commit()

        flash('Registration successful')

        return redirect(url_for('login'))

        return render_template('auth/register.html')

# =========================
# LOGIN
# =========================

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form['username']

        password = request.form['password']

        user = User.query.filter_by(
            username=username
        ).first()

        if user and check_password_hash(user.password, password):

            session['user_id'] = user.id

            session['username'] = user.username

            return redirect(url_for('dashboard'))

        else:

            flash('Invalid username or password')

            return render_template('auth/login.html')
# =========================
# DASHBOARD
# =========================

@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:

        return redirect(url_for('login'))

    logs = VehicleLog.query.order_by(
        VehicleLog.created_at.desc()
    ).all()

    total_scans = VehicleLog.query.count()

    successful_reads = VehicleLog.query.filter(
        VehicleLog.plate_number != 'UNREADABLE'
    ).count()

    todays_scans = total_scans

    return render_template('admin/dashboard.html')
         logs=logs,
        total_scans=total_scans,
        successful_reads=successful_reads,
        todays_scans=todays_scans
    )

# =========================
# UPLOAD
# =========================

@app.route('/upload', methods=['POST'])
def upload():

    if 'user_id' not in session:

        return redirect(url_for('login'))

    if 'image' not in request.files:

        flash('No image uploaded')

        return redirect(url_for('dashboard'))

    file = request.files['image']

    if file.filename == '':

        flash('No selected file')

        return redirect(url_for('dashboard'))

    filename = secure_filename(file.filename)

    filepath = os.path.join(
        app.config['UPLOAD_FOLDER'],
        filename
    )

    file.save(filepath)

    # =========================
    # OCR PROCESSING
    # =========================

    img = cv2.imread(filepath)

    gray = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.bilateralFilter(
        gray,
        11,
        17,
        17
    )

    plate_text = pytesseract.image_to_string(gray)

    plate_text = ''.join(
        e for e in plate_text if e.isalnum()
    )

    plate_text = plate_text.upper().strip()

    if not plate_text:

        plate_text = 'UNREADABLE'

    # =========================
    # S3 UPLOAD
    # =========================

    s3.upload_file(
        filepath,
        S3_BUCKET,
        filename
    )

    image_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{filename}"

    # =========================
    # SAVE DATABASE
    # =========================

    log = VehicleLog(
        user_id=session['user_id'],
        plate_number=plate_text,
        image_url=image_url
    )

    db.session.add(log)

    db.session.commit()

    flash(f'Plate detected: {plate_text}')

    return redirect(url_for('dashboard'))

# =========================
# LOGOUT
# =========================

@app.route('/logout')
def logout():

    session.clear()

    return redirect(url_for('login'))

# =========================
# MAIN
# =========================

if __name__ == '__main__':

    with app.app_context():

        db.create_all()

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
