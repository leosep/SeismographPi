from datetime import datetime
from app import db


class GeophoneSample(db.Model):
    """High-frequency raw samples from the ADC (e.g. 100 Hz).

    Written exclusively by the acquisition daemon. This table grows fast
    (100 rows/sec ~= 8.6M rows/day), so the daemon also prunes old rows
    (see acquisition/daemon.py PRUNE_AFTER_SECONDS).
    """
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    value = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<GeophoneSample {self.timestamp} {self.value}>'

    def to_dict(self):
        return {'timestamp': self.timestamp.isoformat(), 'value': self.value}


class SeismicEvent(db.Model):
    """A P-wave detection produced by the STA/LTA algorithm.

    One row per detected event (trigger -> de-trigger).
    """
    id = db.Column(db.Integer, primary_key=True)
    triggered_at = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)
    peak_ratio = db.Column(db.Float, nullable=False)   # max STA/LTA reached
    peak_value = db.Column(db.Integer, nullable=False)  # max raw amplitude during event

    def __repr__(self):
        return f'<SeismicEvent {self.triggered_at} ratio={self.peak_ratio:.2f}>'

    def to_dict(self):
        return {
            'id': self.id,
            'triggered_at': self.triggered_at.isoformat(),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'peak_ratio': self.peak_ratio,
            'peak_value': self.peak_value,
        }
