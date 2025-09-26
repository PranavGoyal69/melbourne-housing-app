"""
Run after training:
    cd app
    pip install -r requirements.txt
    streamlit run streamlit_app.py
"""
import joblib, pandas as pd, streamlit as st
from pathlib import Path

st.set_page_config(page_title="Melbourne Housing Price Predictor", page_icon="🏠", layout="centered")

OUT_DIR = Path(__file__).resolve().parents[1] / "modeling" / "outputs"
MODEL_PATH = OUT_DIR / "pipeline.pkl"

st.title("🏠 Melbourne Housing Price Predictor")
st.write("Provide property details and get a predicted sale price.")

if not MODEL_PATH.exists():
    st.error("Model file not found. Please run training first to create 'pipeline.pkl'.")
    st.stop()

pipe = joblib.load(MODEL_PATH)

suburb = st.text_input("Suburb", "Essendon")
property_type = st.selectbox("Property Type", ["House","Townhouse","Unit","Apartment","Villa","Other"])
postcode = st.text_input("Postcode", "3040")
agency = st.text_input("Agency (optional)", "")

bedrooms = st.number_input("Bedrooms", min_value=0, max_value=10, value=3, step=1)
bathrooms = st.number_input("Bathrooms", min_value=0, max_value=10, value=2, step=1)
car_spaces = st.number_input("Car Spaces", min_value=0, max_value=8, value=2, step=1)
land_size_sqm = st.number_input("Land Size (sqm)", min_value=0, max_value=10000, value=350, step=10)
building_size_sqm = st.number_input("Building Size (sqm)", min_value=0, max_value=2000, value=160, step=10)
year_built = st.number_input("Year Built", min_value=1800, max_value=2100, value=2015, step=1)
nearby_schools_count = st.number_input("Nearby schools (count)", min_value=0, max_value=50, value=3, step=1)
distance_to_cbd_km = st.number_input("Distance to CBD (km)", min_value=0, max_value=100, value=10, step=1)

has_garage = st.checkbox("Has Garage")
has_aircon = st.checkbox("Has Air Conditioning")
has_heating = st.checkbox("Has Heating")

latitude = st.number_input("Latitude (optional)", value=-37.75)
longitude = st.number_input("Longitude (optional)", value=144.92)

sale_year = st.number_input("Sale Year", min_value=2000, max_value=2100, value=2024, step=1)
sale_month = st.number_input("Sale Month", min_value=1, max_value=12, value=8, step=1)

if st.button("Predict Price"):
    row = pd.DataFrame([{
        "suburb": suburb,
        "property_type": property_type,
        "postcode": postcode if postcode else None,
        "agency": agency if agency else None,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "car_spaces": car_spaces,
        "land_size_sqm": land_size_sqm,
        "building_size_sqm": building_size_sqm,
        "year_built": year_built,
        "nearby_schools_count": nearby_schools_count,
        "distance_to_cbd_km": distance_to_cbd_km,
        "has_garage": int(has_garage),
        "has_aircon": int(has_aircon),
        "has_heating": int(has_heating),
        "latitude": latitude,
        "longitude": longitude,
        "sale_year": sale_year,
        "sale_month": sale_month,
    }])
    pred = pipe.predict(row)[0]
    st.success(f"Estimated Price: ${pred:,.0f}")
