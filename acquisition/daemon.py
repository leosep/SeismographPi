"""
Geophone acquisition daemon.

Runs independently of Flask (as a systemd service). Responsibilities:

1. Sample the ADS1115 ADC at a fixed rate (SAMPLE_RATE_HZ), regardless of
   whether anyone has a browser open.
2. Feed each sample into a streaming STA/LTA detector to flag P-wave
   arrivals in near real time.
3. Persist raw samples to SQLite (for the chart) and persist detected
   events to a separate table (for alerts).
4. Publish detected events to a small local file-based queue that the
   Flask app's SSE endpoint reads from, so the browser gets notified
   within ~1 second of a detection.

Run with:
    python -m acquisition.daemon

Or install as a systemd service (see acquisition/geophone-daemon.service).
"""
import json
import os
import sys
import time
import collections
from datetime import datetime, timezone

import Adafruit_ADS1x15

# Make the Flask app's package importable so we can reuse its db/models
# instead of duplicating the schema.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import GeophoneSample, SeismicEvent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SAMPLE_RATE_HZ = 100          # Nyquist needs >= 2x the highest frequency of
                               # interest. P-waves carry energy up to ~10-20 Hz,
                               # so 100 Hz gives comfortable margin.
SAMPLE_PERIOD_S = 1.0 / SAMPLE_RATE_HZ

ADC_CHANNEL_GAIN = 16         # +/-0.256V range; tune to your geophone's
                               # output voltage swing (see HW-484/amplifier
                               # board datasheet).

STA_WINDOW_S = 0.5            # Short-term average window: should be a bit
                               # longer than a single P-wave cycle.
LTA_WINDOW_S = 20.0           # Long-term average window: should span several
                               # times the longest expected seismic period,
                               # so it represents "background noise", not signal.

TRIGGER_RATIO = 4.0           # STA/LTA ratio that declares "event started".
                               # 3-6 is the typical range used in seismology.
DETRIGGER_RATIO = 1.5         # STA/LTA ratio that declares "event ended".

MIN_EVENT_DURATION_S = 0.3    # Ignore single-sample spikes (e.g. electrical
                               # noise, someone bumping the table).

DB_WRITE_BATCH_SIZE = 20      # Buffer raw samples and write in batches to
                               # avoid hammering SQLite at 100 writes/sec.

PRUNE_AFTER_SECONDS = 3600    # Keep only the last hour of raw samples in the
                               # DB; older rows are deleted. Adjust to your
                               # disk size / retention needs.
PRUNE_INTERVAL_S = 60         # How often to run the prune.

EVENTS_QUEUE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'events_queue.jsonl'
)


class StreamingSTALTA:
    """Maintains running sums for STA and LTA so each new sample is O(1),
    instead of recomputing the average over the whole window every time.
    """

    def __init__(self, sample_rate_hz, sta_window_s, lta_window_s):
        self.sta_len = max(1, int(sta_window_s * sample_rate_hz))
        self.lta_len = max(1, int(lta_window_s * sample_rate_hz))
        self.sta_buf = collections.deque(maxlen=self.sta_len)
        self.lta_buf = collections.deque(maxlen=self.lta_len)
        self.sta_sum = 0.0
        self.lta_sum = 0.0

    def update(self, value):
        # STA/LTA conventionally operates on signal *energy* (squared
        # amplitude), not raw amplitude, so it's insensitive to sign/offset.
        energy = float(value) ** 2

        if len(self.sta_buf) == self.sta_buf.maxlen:
            self.sta_sum -= self.sta_buf[0]
        self.sta_buf.append(energy)
        self.sta_sum += energy

        if len(self.lta_buf) == self.lta_buf.maxlen:
            self.lta_sum -= self.lta_buf[0]
        self.lta_buf.append(energy)
        self.lta_sum += energy

        sta = self.sta_sum / len(self.sta_buf)
        # Require the LTA window to be reasonably full before trusting it;
        # otherwise the ratio is wildly noisy right after startup.
        if len(self.lta_buf) < self.lta_buf.maxlen * 0.5:
            return sta, None

        lta = self.lta_sum / len(self.lta_buf)
        if lta <= 1e-9:
            return sta, None

        return sta, sta / lta


def read_adc(adc):
    try:
        return adc.read_adc_difference(0, gain=ADC_CHANNEL_GAIN)
    except Exception as exc:
        print(f'[acquisition] ADC read error: {exc}', flush=True)
        return None


def publish_event(event_dict):
    """Append the event as one JSON line. The Flask SSE endpoint tails
    this file. A file is used instead of an in-memory queue because the
    daemon and the Flask process are separate OS processes.
    """
    os.makedirs(os.path.dirname(EVENTS_QUEUE_PATH), exist_ok=True)
    with open(EVENTS_QUEUE_PATH, 'a') as f:
        f.write(json.dumps(event_dict) + '\n')


def run():
    app = create_app()
    adc = Adafruit_ADS1x15.ADS1115(address=0x48, busnum=1)
    detector = StreamingSTALTA(SAMPLE_RATE_HZ, STA_WINDOW_S, LTA_WINDOW_S)

    sample_batch = []
    in_event = False
    event_start = None
    event_peak_ratio = 0.0
    event_peak_value = 0

    last_prune = time.time()
    next_tick = time.monotonic()

    print(f'[acquisition] starting at {SAMPLE_RATE_HZ} Hz '
          f'(STA={STA_WINDOW_S}s, LTA={LTA_WINDOW_S}s, '
          f'trigger={TRIGGER_RATIO}, detrigger={DETRIGGER_RATIO})', flush=True)

    with app.app_context():
        while True:
            value = read_adc(adc)
            now = datetime.now(timezone.utc)

            if value is not None:
                sample_batch.append(GeophoneSample(timestamp=now, value=value))
                sta, ratio = detector.update(value)

                if ratio is not None:
                    if not in_event and ratio >= TRIGGER_RATIO:
                        in_event = True
                        event_start = now
                        event_peak_ratio = ratio
                        event_peak_value = value
                        print(f'[acquisition] P-wave trigger at {now.isoformat()} '
                              f'ratio={ratio:.2f}', flush=True)

                    elif in_event:
                        event_peak_ratio = max(event_peak_ratio, ratio)
                        if abs(value) > abs(event_peak_value):
                            event_peak_value = value

                        if ratio <= DETRIGGER_RATIO:
                            duration = (now - event_start).total_seconds()
                            in_event = False
                            if duration >= MIN_EVENT_DURATION_S:
                                evt = SeismicEvent(
                                    triggered_at=event_start,
                                    ended_at=now,
                                    peak_ratio=event_peak_ratio,
                                    peak_value=event_peak_value,
                                )
                                db.session.add(evt)
                                db.session.commit()
                                print(f'[acquisition] P-wave event saved: '
                                      f'id={evt.id} duration={duration:.2f}s '
                                      f'peak_ratio={event_peak_ratio:.2f}', flush=True)
                                publish_event(evt.to_dict())
                            else:
                                print(f'[acquisition] discarded short blip '
                                      f'({duration:.2f}s < {MIN_EVENT_DURATION_S}s)',
                                      flush=True)

            if len(sample_batch) >= DB_WRITE_BATCH_SIZE:
                db.session.bulk_save_objects(sample_batch)
                db.session.commit()
                sample_batch.clear()

            if time.time() - last_prune > PRUNE_INTERVAL_S:
                cutoff = datetime.now(timezone.utc).timestamp() - PRUNE_AFTER_SECONDS
                cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
                db.session.query(GeophoneSample).filter(
                    GeophoneSample.timestamp < cutoff_dt
                ).delete()
                db.session.commit()
                last_prune = time.time()

            # Fixed-rate scheduling: sleep until the next tick rather than
            # sleeping a flat SAMPLE_PERIOD_S, so ADC/DB jitter doesn't
            # accumulate drift over time.
            next_tick += SAMPLE_PERIOD_S
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                # We're falling behind (DB write took too long, etc).
                # Reset the schedule instead of trying to "catch up" with
                # zero sleeps, which would peg the CPU.
                next_tick = time.monotonic()


if __name__ == '__main__':
    run()
