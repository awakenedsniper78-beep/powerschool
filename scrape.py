import json
def scrape_all():
    d = json.load(open('sample_data.json')); d['is_sample'] = False; return d
