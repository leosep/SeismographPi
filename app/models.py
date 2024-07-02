from datetime import datetime
from app import db

class GeophoneRecords(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    value = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<GeophoneRecords {self.timestamp} {self.value}>'
