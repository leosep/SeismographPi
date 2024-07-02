from flask import Blueprint, render_template, jsonify
from app.utils import read_geophone_data_and_save
from app.models import GeophoneRecords

main = Blueprint('main', __name__)

@main.route('/')
def index():
    return render_template('index.html')

@main.route('/data')
def get_data():
    # Fetch data from the database
    data_points = GeophoneRecords.query.order_by(GeophoneRecords.timestamp.asc()).all()
    timestamps = [data.timestamp for data in data_points]
    values = [data.value for data in data_points]

    return jsonify({
        'timestamps': timestamps,
        'values': values
    })

@main.route('/save_geophone_data', methods=['POST'])
def save_geophone_data():
    value = read_geophone_data_and_save()
    if value is not None:
        return f'Geophone data saved: {value}', 200
    else:
        return 'Failed to save geophone data', 500
