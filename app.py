from flask import Flask, request, render_template, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///park_with_ease.db'
app.config['SECRET_KEY'] = 'supersecretkey'
db = SQLAlchemy(app)

# Models
class User(db.Model):
    __tablename__ = 'Our_Users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    vehicle_number = db.Column(db.String(20), nullable=False)
    reservations = db.relationship('Reservation', backref='user', lazy=True)

class ParkingLot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prime_location_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(200), nullable=False)
    pin_code = db.Column(db.String(10), nullable=False)
    max_spots = db.Column(db.Integer, nullable=False)
    spots = db.relationship('ParkingSpot', backref='lot', lazy=True)

class ParkingSpot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lot.id'), nullable=False)
    status = db.Column(db.String(1), nullable=False, default='A')  # A or O
    reservations = db.relationship('Reservation', backref='spot', lazy=True)

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spot.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('Our_Users.id'), nullable=False)
    parking_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    leaving_timestamp = db.Column(db.DateTime, nullable=True)
    price_per_unit = db.Column(db.Float, nullable=False)

# Routes
@app.route('/')
def home_page():
    return render_template("home.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Admin login
        if username == 'admin@123' and password == 'boss':
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            return redirect(url_for('user_dashboard'))

        return render_template("login.html", error="Invalid credentials. Please try again.")

    return render_template("login.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        dob = datetime.strptime(request.form['dob'], '%Y-%m-%d').date()
        vehicle_number = request.form['vehicle_number']

        if User.query.filter_by(username=username).first():
            return "<h2>Username already exists!</h2>"

        hashed = generate_password_hash(password)
        user = User(username=username, password=hashed, dob=dob, vehicle_number=vehicle_number)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template("register.html")

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('login'))

    lots = ParkingLot.query.all()
    total_lots = len(lots)
    total_spots = ParkingSpot.query.count()
    total_occupied = ParkingSpot.query.filter_by(status='O').count()
    total_available = total_spots - total_occupied
    users = User.query.all()

    # Count occupied/available per lot
    for lot in lots:
        lot.occupied = ParkingSpot.query.filter_by(lot_id=lot.id, status='O').count()
        lot.available = ParkingSpot.query.filter_by(lot_id=lot.id, status='A').count()

    # Chart data preparation
    chart_labels = []
    chart_data = []

    for user in users:
        latest_res = Reservation.query.filter_by(user_id=user.id).order_by(Reservation.parking_timestamp.desc()).first()
        if latest_res and latest_res.leaving_timestamp:
            duration = (latest_res.leaving_timestamp - latest_res.parking_timestamp).total_seconds() / 60
            cost = round(duration * latest_res.price_per_unit, 2)
            chart_labels.append(user.username)
            chart_data.append(cost)

    return render_template("admin_dashboard.html",
                           lots=lots,
                           total_lots=total_lots,
                           total_spots=total_spots,
                           total_occupied=total_occupied,
                           total_available=total_available,
                           users=users,
                           chart_labels=chart_labels,
                           chart_data=chart_data)

@app.route('/admin/create_lot', methods=['GET', 'POST'])
def create_lot():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        lot = ParkingLot(
            prime_location_name=request.form['location'],
            price=float(request.form['price']),
            address=request.form['address'],
            pin_code=request.form['pin_code'],
            max_spots=int(request.form['max_spots'])
        )
        db.session.add(lot)
        db.session.commit()

        for _ in range(lot.max_spots):
            spot = ParkingSpot(lot_id=lot.id)
            db.session.add(spot)
        db.session.commit()
        return redirect(url_for('admin_dashboard'))

    return render_template("create_lot.html")

@app.route('/admin/delete_lot/<int:lot_id>')
def delete_lot(lot_id):
    if not session.get('admin'):
        return redirect(url_for('login'))

    lot = ParkingLot.query.get_or_404(lot_id)
    occupied = ParkingSpot.query.filter_by(lot_id=lot.id, status='O').first()
    if occupied:
        return "<h2>Cannot delete lot with active reservations.</h2><a href='/admin'>Back</a>"

    ParkingSpot.query.filter_by(lot_id=lot.id).delete()
    db.session.delete(lot)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_lot/<int:lot_id>', methods=['GET', 'POST'])
def edit_lot(lot_id):
    if not session.get('admin'):
        return redirect(url_for('login'))

    lot = ParkingLot.query.get_or_404(lot_id)

    if request.method == 'POST':
        lot.prime_location_name = request.form['location']
        lot.price = float(request.form['price'])
        lot.address = request.form['address']
        lot.pin_code = request.form['pin_code']
        new_max_spots = int(request.form['max_spots'])

        if new_max_spots > lot.max_spots:
            for _ in range(new_max_spots - lot.max_spots):
                new_spot = ParkingSpot(lot_id=lot.id)
                db.session.add(new_spot)
        lot.max_spots = new_max_spots

        db.session.commit()
        return redirect(url_for('admin_dashboard'))

    return render_template("edit_lot.html", lot=lot)

@app.route('/admin/spot_status/<int:lot_id>')
def spot_status(lot_id):
    if not session.get('admin'):
        return redirect(url_for('login'))

    lot = ParkingLot.query.get_or_404(lot_id)
    spots = ParkingSpot.query.filter_by(lot_id=lot_id).all()
    spot_details = []

    for spot in spots:
        if spot.status == 'O':
            reservation = Reservation.query.filter_by(spot_id=spot.id).order_by(Reservation.parking_timestamp.desc()).first()
            user = User.query.get(reservation.user_id) if reservation else None
            spot_details.append({'spot': spot, 'reservation': reservation, 'user': user})
        else:
            spot_details.append({'spot': spot, 'reservation': None, 'user': None})

    return render_template("spot_status.html", lot=lot, spot_details=spot_details)

@app.route('/admin/users')
def view_users():
    if not session.get('admin'):
        return redirect(url_for('login'))

    users = User.query.all()
    return render_template('view_users.html', users=users)

@app.route('/user')
def user_dashboard():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    lots = ParkingLot.query.all()
    for lot in lots:
        lot.available_spots = ParkingSpot.query.filter_by(lot_id=lot.id, status='A').count()

    reservations = Reservation.query.filter_by(user_id=user.id).order_by(Reservation.parking_timestamp.desc()).all()

    chart_labels = []
    chart_data = []

    completed = 0
    ongoing = 0

    for res in reservations:
        if res.leaving_timestamp:
            completed += 1
            duration = (res.leaving_timestamp - res.parking_timestamp).total_seconds() / 60
            cost = round(duration * res.price_per_unit, 2)
            chart_labels.append(f"Booking #{res.id}")
            chart_data.append(cost)
        else:
            ongoing += 1

    return render_template("user_dashboard.html",
                           lots=lots,
                           reservations=reservations,
                           user=user,
                           chart_labels=chart_labels,
                           chart_data=chart_data,
                           user_completed=completed,
                           user_ongoing=ongoing)

@app.route('/user/book/<int:lot_id>')
def book_spot(lot_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    spot = ParkingSpot.query.filter_by(lot_id=lot_id, status='A').first()
    if spot:
        spot.status = 'O'
        reservation = Reservation(spot_id=spot.id, user_id=session['user_id'], price_per_unit=spot.lot.price)
        db.session.add(reservation)
        db.session.commit()
        flash(f"Spot #{spot.id} booked successfully!", "success")
    else:
        flash("No available spots!", "danger")

    return redirect(url_for('user_dashboard'))

@app.route('/user/release/<int:spot_id>')
def release_spot(spot_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    reservation = Reservation.query.filter_by(spot_id=spot_id, user_id=session['user_id'], leaving_timestamp=None).first()
    if reservation:
        reservation.leaving_timestamp = datetime.utcnow()
        duration = (reservation.leaving_timestamp - reservation.parking_timestamp).total_seconds() / 60
        cost = round(duration * reservation.price_per_unit, 2)
        spot = ParkingSpot.query.get(spot_id)
        spot.status = 'A'
        db.session.commit()
        flash(f"Spot #{spot.id} released. Duration: {duration:.2f} min | Cost: ₹{cost:.2f}", "success")
    else:
        flash("No active reservation found!", "warning")

    return redirect(url_for('user_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home_page'))

# Initialize DB and ensure admin exists
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin@123').first():
            db.session.add(User(
                username='admin@123',
                password=generate_password_hash('boss'),
                dob=datetime(1990, 1, 1),
                vehicle_number='ADMIN123'
            ))
            db.session.commit()
    app.run(debug=True)

# Remove the lock file if it exists
try:
    os.remove(".git/index.lock")
except FileNotFoundError:
    pass
