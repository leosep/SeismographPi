import json
import os
import time

from flask import Blueprint, render_template, jsonify, Response, current_app

from app.models import GeophoneSample, SeismicEvent

main = Blueprint('main', __name__)

EVENTS_QUEUE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'events_queue.jsonl'
)


@main.route('/')
def index():
    return render_template('index.html')


@main.route('/data')
def get_data():
    """Returns the most recent raw samples for the chart.

    Only the daemon writes samples now, so this is read-only and cheap.
    Limited to the last N points to keep the response small at 100 Hz.
    """
    limit = 1000  # 10 seconds of data at 100 Hz
    data_points = (
        GeophoneSample.query
        .order_by(GeophoneSample.timestamp.desc())
        .limit(limit)
        .all()
    )
    data_points.reverse()  # chronological order for the chart

    return jsonify({
        'timestamps': [d.timestamp.isoformat() for d in data_points],
        'values': [d.value for d in data_points],
    })


@main.route('/events')
def get_recent_events():
    """Returns recently detected P-wave events (for page load / history)."""
    events = (
        SeismicEvent.query
        .order_by(SeismicEvent.triggered_at.desc())
        .limit(20)
        .all()
    )
    return jsonify([e.to_dict() for e in events])


@main.route('/events/stream')
def stream_events():
    """Server-Sent Events endpoint: pushes a new event to the browser the
    moment the acquisition daemon detects and publishes one.

    Implementation note: the daemon appends JSON lines to a file
    (EVENTS_QUEUE_PATH) because it runs as a separate OS process from
    Flask, so we tail that file rather than sharing in-memory state.
    """
    def event_stream():
        # Start tailing from the end of the file so we only get events
        # detected from now on, not the entire history.
        last_size = 0
        if os.path.exists(EVENTS_QUEUE_PATH):
            last_size = os.path.getsize(EVENTS_QUEUE_PATH)

        while True:
            if os.path.exists(EVENTS_QUEUE_PATH):
                current_size = os.path.getsize(EVENTS_QUEUE_PATH)
                if current_size > last_size:
                    with open(EVENTS_QUEUE_PATH, 'r') as f:
                        f.seek(last_size)
                        new_lines = f.read()
                    last_size = current_size
                    for line in new_lines.strip().split('\n'):
                        if line:
                            yield f'data: {line}\n\n'
                elif current_size < last_size:
                    # File was rotated/truncated externally; restart from 0.
                    last_size = 0

            # SSE keep-alive comment so proxies/browsers don't time out
            # the connection during quiet periods.
            yield ': keep-alive\n\n'
            time.sleep(1)

    return Response(event_stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',  # disable nginx buffering if proxied
    })
