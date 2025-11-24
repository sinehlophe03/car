import os
import logging
import traceback
from datetime import datetime, date

from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify
)
from flask_sqlalchemy import SQLAlchemy

# --- Configuration & Initialization ---
app = Flask(__name__)

# Load SECRET_KEY from environment or use a fallback
app.secret_key = os.environ.get('SECRET_KEY', 'royalrinse-secret')

# Configure SQLAlchemy
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, 'royalrinse.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Logging Setup ---
logger = logging.getLogger('royalrinse')
logger.setLevel(logging.INFO)

# Only add handler if not already present (prevents duplicate logs in reloader)
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

# --- Constants ---
DEFAULT_SLOTS = ['08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00']
SERVICE_PRICES = {'basic': 15.0, 'deluxe': 30.0, 'royal': 50.0}

# --- Database Model ---
class Booking(db.Model):
    """Database model for a car wash booking."""
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(140), nullable=False)
    phone = db.Column(db.String(60))
    service = db.Column(db.String(80), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(255))
    notes = db.Column(db.Text)
    status = db.Column(db.String(30), default='accepted')  # 'accepted' or 'rejected'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(db.Float, default=0.0)

    def __repr__(self):
        return f"<Booking {self.id}: {self.date} {self.time} - {self.customer_name}>"

# Create database tables if they don't exist
with app.app_context():
    db.create_all()

# --- Helper Functions ---
def available_slots_for(d: date) -> list[str]:
    """
    Computes available time slots for a given date 'd'.

    Args:
        d: The date object to check for bookings.

    Returns:
        A list of available time slot strings.
    """
    if d is None:
        return DEFAULT_SLOTS.copy()

    try:
        # Find all accepted bookings for the specific date
        taken = [
            b.time for b in Booking.query.filter_by(date=d, status='accepted').all()
        ]
        # Return slots that are NOT in the taken list
        return [s for s in DEFAULT_SLOTS if s not in taken]
    except Exception:
        logger.error('Error computing slots: %s', traceback.format_exc())
        return DEFAULT_SLOTS.copy()

# --- Context Processors ---
@app.context_processor
def inject_common():
    """Injects common variables into all templates."""
    contact = {
        'phone': '76716978',
        'email': 'royalrinse07@gmail.com',
        'location': 'Mbabane (Sidwashini)'
    }
    return {
        'current_year': datetime.utcnow().year,
        'contact': contact
    }

# --- Routes ---
@app.route('/')
def index():
    """Renders the main homepage."""
    locations = ['Mbabane (Sidwashini)']
    services = [
        {'id': 'basic', 'title': 'Basic Rinse', 'price': SERVICE_PRICES['basic'],
         'desc': 'Exterior wash & dry'},
        {'id': 'deluxe', 'title': 'Deluxe Rinse', 'price': SERVICE_PRICES['deluxe'],
         'desc': 'Exterior + interior vacuum'},
        {'id': 'royal', 'title': 'Royal Rinse', 'price': SERVICE_PRICES['royal'],
         'desc': 'Full detail: wax, polish, deep interior clean'}
    ]
    return render_template('index.html', services=services, locations=locations)

@app.route('/book', methods=['GET', 'POST'])
def book():
    """Handles the booking form submission and displays the booking page."""
    message = None
    if request.method == 'POST':
        name = request.form.get('customer_name')
        phone = request.form.get('phone')
        service = request.form.get('service') or 'basic'
        date_str = request.form.get('date')
        time_slot = request.form.get('time')
        address = request.form.get('address')
        notes = request.form.get('notes')
        
        # 1. Basic validation
        if not all([name, phone, date_str, time_slot, address]):
            message = ('error', 'Please fill all required fields.')
            return render_template('book.html', message=message)

        # 2. Date format validation
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            message = ('error', 'Invalid date format.')
            return render_template('book.html', message=message)
        
        # 3. Time slot validation (Check for prior acceptance)
        occupied = Booking.query.filter_by(
            date=d, time=time_slot, status='accepted'
        ).first()
        
        # Determine the price
        price = SERVICE_PRICES.get(service, 15.0)

        # Prepare the new booking object
        new_booking = Booking(
            customer_name=name,
            phone=phone,
            service=service,
            date=d,
            time=time_slot,
            address=address,
            notes=notes,
            amount=price
        )

        if occupied:
            # 4. Reject and log the rejected booking
            new_booking.status = 'rejected'
            db.session.add(new_booking)
            db.session.commit()
            logger.warning("Rejected booking for %s on %s at %s. Slot taken.", name, d, time_slot)
            message = ('reject', f'Timeslot **{time_slot}** on **{d}** is already taken — booking rejected. Please choose another slot.')
        else:
            # 5. Accept and log the accepted booking
            new_booking.status = 'accepted'
            db.session.add(new_booking)
            db.session.commit()
            logger.info("Accepted booking for %s on %s at %s.", name, d, time_slot)
            message = ('accept', f'✅ Booking accepted for **{time_slot}** on **{d}**. We look forward to seeing you!')

        return render_template('book.html', message=message)
    
    # GET request: Render the empty booking form
    return render_template('book.html', message=message)

@app.route('/api/slots')
def api_slots():
    """API endpoint to get available time slots for a given date."""
    date_str = request.args.get('date')
    
    if not date_str:
        # Return default slots if no date is provided
        return jsonify({'slots': available_slots_for(None)})
    
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        # Return an empty list for invalid date strings
        return jsonify({'slots': []})
        
    return jsonify({'slots': available_slots_for(d)})

@app.route('/schedule')
def schedule():
    """Renders the schedule page, showing accepted bookings for a selected date."""
    date_str = request.args.get('date')
    
    try:
        # Attempt to parse the date from the query parameter
        if date_str:
            selected = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            selected = date.today()
    except ValueError:
        # Fallback to today's date on error
        selected = date.today()
        
    # Retrieve accepted bookings for the selected date, ordered by time
    bookings = Booking.query.filter_by(
        date=selected, status='accepted'
    ).order_by(Booking.time).all()
    
    return render_template('schedule.html', bookings=bookings, today=selected)

@app.route('/bookings.json')
def bookings_json():
    """API endpoint to get all bookings in JSON format."""
    all_b = Booking.query.order_by(Booking.date.desc(), Booking.time).all()
    
    bookings_list = [{
        'id': b.id,
        'customer_name': b.customer_name,
        'phone': b.phone,
        'date': b.date.isoformat() if b.date else None,
        'time': b.time,
        'service': b.service,
        'status': b.status,
        'amount': b.amount
    } for b in all_b]
    
    return jsonify(bookings_list)

# --- Run Application ---
if __name__ == '__main__':
    # Use environment port if available, otherwise default to 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)