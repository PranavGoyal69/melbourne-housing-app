import streamlit as st
import pandas as pd
import joblib

# Load trained model
pipe = joblib.load("melb_price_model.joblib")

st.title("🏠 Melbourne Housing Price Predictor")

suburb = st.text_input("Suburb", "Essendon")
ptype = st.selectbox("Property Type", ["House", "Apartment"])
agent = st.text_input("Agent", "Unknown")
bedrooms = st.number_input("Bedrooms", 1, 10, 3)
bathrooms = st.number_input("Bathrooms", 1, 10, 2)
car_spaces = st.number_input("Car Spaces", 0, 5, 2)
land_size = st.number_input("Land Size (sqm)", 0, 2000, 400)
sale_year = st.number_input("Sale Year", 2015, 2030, 2025)
sale_month = st.number_input("Sale Month", 1, 12, 7)

rooms_total = bedrooms + bathrooms
density_bed_per_100sqm = 0 if land_size == 0 else bedrooms / (land_size/100)
is_house = 1 if "house" in ptype.lower() else 0
is_apartment = 1 if ("apart" in ptype.lower() or "unit" in ptype.lower()) else 0

if st.button("Predict Price"):
    row = pd.DataFrame([{
        "suburb": suburb,
        "property_type": ptype,
        "agent": agent,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "car_spaces": car_spaces,
        "land_size_sqm": land_size,
        "sale_year": sale_year,
        "sale_month": sale_month,
        "rooms_total": rooms_total,
        "density_bed_per_100sqm": density_bed_per_100sqm,
        "is_house": is_house,
        "is_apartment": is_apartment
    }])
    price = pipe.predict(row)[0]
    st.success(f"Estimated Price: ${price:,.0f}")
