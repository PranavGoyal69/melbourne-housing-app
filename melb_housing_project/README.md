# Melbourne Housing Price Project (Essendon, Bentleigh, Burwood)

## Quick Start
1) Scrape data
```bash
cd scraper
pip install selenium webdriver-manager pandas
python rea_scraper.py
```
This saves `../data/melbourne_housing.csv`.

2) Train models
```bash
cd ../modeling
pip install -r requirements.txt
python train_models.py --csv ../data/melbourne_housing.csv
```
Outputs in `modeling/outputs`: `model_compare.csv`, `metrics.json`, `pipeline.pkl`, `eda/*.png`.

3) Run the app
```bash
cd ../app
pip install -r requirements.txt
streamlit run streamlit_app.py
```

If you prefer manual data entry, use `data/melbourne_housing_template.csv` (≥150 rows).

**Note:** Scraper is educational; respect website Terms of Use.
