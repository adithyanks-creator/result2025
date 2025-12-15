import json
import os
from pathlib import Path

# Base directory containing the organizational district folders
base_dir = Path("/Users/varahelap/Downloads/Reults map db/kerala_lb_by_org_district")

# List of all 30 organizational districts
districts = [
    "Alappuzha North", "Alappuzha South", "Ernakulam City", "Ernakulam East", "Ernakulam North",
    "Idukki North", "Idukki South", "Kannur North", "Kannur South", "Kasaragod",
    "Kollam East", "Kollam West", "Kottayam East", "Kottayam West", "Kozhikode City",
    "Kozhikode North", "Kozhikode Rural", "Malappuram Central", "Malappuram East", "Malappuram West",
    "Palakkad East", "Palakkad West", "Pathanamthitta", "Thiruvananthapuram City", 
    "Thiruvananthapuram North", "Thiruvananthapuram South", "Thrissur City", "Thrissur North",
    "Thrissur South", "Wayanad"
]

def extract_all_features(data):
    """Recursively extract all GeoJSON features from the hierarchy"""
    features = []
    
    if isinstance(data, dict):
        # Check if this dict has a geojson key with features
        if 'geojson' in data and isinstance(data['geojson'], dict):
            geojson = data['geojson']
            if 'features' in geojson and isinstance(geojson['features'], list):
                features.extend(geojson['features'])
        
        # Recursively check all values
        for key, value in data.items():
            if key != 'geojson':  # Skip geojson since we already processed it
                features.extend(extract_all_features(value))
    
    elif isinstance(data, list):
        for item in data:
            features.extend(extract_all_features(item))
    
    return features

def count_local_bodies(data):
    """Count the number of local bodies in the hierarchy"""
    count = 0
    
    if isinstance(data, dict):
        if 'local_bodies' in data and isinstance(data['local_bodies'], list):
            count += len(data['local_bodies'])
        for key, value in data.items():
            count += count_local_bodies(value)
    elif isinstance(data, list):
        for item in data:
            count += count_local_bodies(item)
    
    return count

# Process all districts
all_districts_data = []

for district_name in districts:
    district_folder = base_dir / district_name
    json_file = district_folder / f"{district_name}_hierarchy_with_geojson.json"
    
    if json_file.exists():
        print(f"Processing: {district_name}")
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract all features
            features = extract_all_features(data)
            lb_count = count_local_bodies(data)
            
            # Create a combined GeoJSON for this district
            combined_geojson = {
                "type": "FeatureCollection",
                "features": features
            }
            
            all_districts_data.append({
                "name": district_name,
                "lbCount": lb_count,
                "geojson": combined_geojson
            })
            
            print(f"  - Found {len(features)} polygon features, {lb_count} local bodies")
            
        except Exception as e:
            print(f"  - Error processing {district_name}: {e}")
            all_districts_data.append({
                "name": district_name,
                "lbCount": 0,
                "geojson": {"type": "FeatureCollection", "features": []}
            })
    else:
        print(f"File not found: {json_file}")
        all_districts_data.append({
            "name": district_name,
            "lbCount": 0,
            "geojson": {"type": "FeatureCollection", "features": []}
        })

# Read the HTML template
html_template_path = Path("/Users/varahelap/Downloads/Reults map db/kerala_org_districts_map.html")
with open(html_template_path, 'r', encoding='utf-8') as f:
    html_content = f.read()

# Convert the data to JSON string
districts_json = json.dumps(all_districts_data, ensure_ascii=False)

# Replace placeholder with actual data
html_content = html_content.replace('DISTRICTS_DATA_PLACEHOLDER', districts_json)

# Write the final HTML file
output_path = Path("/Users/varahelap/Downloads/Reults map db/kerala_map.html")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"\n✅ Map generated successfully!")
print(f"📁 Output file: {output_path}")
print(f"📊 Total districts processed: {len(all_districts_data)}")
total_features = sum(len(d['geojson']['features']) for d in all_districts_data)
print(f"🗺️  Total polygon features: {total_features}")
