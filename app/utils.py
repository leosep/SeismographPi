import Adafruit_ADS1x15
from app.models import GeophoneRecords
from app import db

# Create an ADS1115 ADC (16-bit) instance
adc = Adafruit_ADS1x15.ADS1115(address=0x48, busnum=1)

# Choose a gain
GAIN = 16

def read_geophone_data_and_save():
    try:
        # Read geophone data
        value = adc.read_adc_difference(0, gain=GAIN)
        
        # Save to database
        data_point = GeophoneRecords(value=value)
        db.session.add(data_point)
        db.session.commit()

        return value
    except Exception as e:
        print(f'Error reading or saving geophone data: {str(e)}')
        db.session.rollback()
        return None
