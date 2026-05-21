from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'mysecretkey123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///platedb.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

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
    image_path = db.Column(db.String(255))
    entry_time = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()
    admin = User.query.filter_by(email='admin@plate.com').first()
    if not admin:
        hashed = bcrypt.generate_password_hash('admin123').decode('utf-8')
        admin = User(
            name='Admin',
            email='admin@plate.com',
            password_hash=hashed,
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()

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
            user = User(
                name=name,
                email=email,
                password_hash=password
            )
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
        if user and bcrypt.check_password_hash(
            user.password_hash, password):
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
    logs = VehicleLog.query.filter_by(
        user_id=session['user_id']).all()
    total_scans = len(logs)
    successful = len([l for l in logs
                     if l.plate_number != 'UNREADABLE'])
    return render_template('user/dashboard.html',
        logs=logs,
        total_scans=total_scans,
        successful=successful
    )

@app.route('/admin')
def admin_dashboard():
    if session.get('user_role') != 'admin':
        return redirect(url_for('dashboard'))
    total_users = User.query.count()
    total_logs = VehicleLog.query.count()
    recent_logs = VehicleLog.query.order_by(
        VehicleLog.created_at.desc()).limit(10).all()
    return render_template('admin/dashboard.html',
        total_users=total_users,
        total_logs=total_logs,
        recent_logs=recent_logs
    )

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
    filename = file.filename
    filepath = os.path.join('uploads', filename)
    file.save(filepath)
    try:
        import easyocr
        reader = easyocr.Reader(['en'])
        results = reader.readtext(filepath)
        plate_text = ''
        for (bbox, text, prob) in results:
            if prob > 0.3:
                plate_text += text
        plate_text = ''.join(
            e for e in plate_text if e.isalnum()
        )
        plate_text = plate_text.upper().strip()
        if not plate_text:
            plate_text = 'UNREADABLE'
    except Exception as e:
        print(f"Error: {e}")
        plate_text = 'UNREADABLE'
    log = VehicleLog(
        user_id=session['user_id'],
        plate_number=plate_text,
        image_path=filepath
    )
    db.session.add(log)
    db.session.commit()
    flash(f'Plate detected: {plate_text}', 'success')
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True)