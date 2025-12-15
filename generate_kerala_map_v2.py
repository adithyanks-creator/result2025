import json
import os
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

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
        if 'geojson' in data and isinstance(data['geojson'], dict):
            geojson = data['geojson']
            if 'features' in geojson and isinstance(geojson['features'], list):
                features.extend(geojson['features'])
        
        for key, value in data.items():
            if key != 'geojson':
                features.extend(extract_all_features(value))
    
    elif isinstance(data, list):
        for item in data:
            features.extend(extract_all_features(item))
    
    return features

def merge_features_to_boundary(features):
    """Merge all polygon features into a single boundary polygon"""
    polygons = []
    
    for feature in features:
        try:
            geom = feature.get('geometry')
            if geom and geom.get('type') in ['Polygon', 'MultiPolygon']:
                poly = shape(geom)
                if poly.is_valid:
                    polygons.append(poly)
                else:
                    # Try to fix invalid polygon
                    poly = poly.buffer(0)
                    if poly.is_valid:
                        polygons.append(poly)
        except Exception as e:
            continue
    
    if not polygons:
        return None
    
    # Merge all polygons into one
    try:
        merged = unary_union(polygons)
        return merged
    except Exception as e:
        print(f"    Error merging: {e}")
        return None

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
            print(f"  - Found {len(features)} polygon features")
            
            # Merge all features into a single boundary
            merged_boundary = merge_features_to_boundary(features)
            
            if merged_boundary:
                # Convert back to GeoJSON
                merged_geojson = {
                    "type": "FeatureCollection",
                    "features": [{
                        "type": "Feature",
                        "properties": {"name": district_name},
                        "geometry": mapping(merged_boundary)
                    }]
                }
                all_districts_data.append({
                    "name": district_name,
                    "geojson": merged_geojson
                })
                print(f"  ✓ Merged into boundary successfully")
            else:
                print(f"  ✗ Failed to merge")
                all_districts_data.append({
                    "name": district_name,
                    "geojson": {"type": "FeatureCollection", "features": []}
                })
            
        except Exception as e:
            print(f"  - Error processing {district_name}: {e}")
            all_districts_data.append({
                "name": district_name,
                "geojson": {"type": "FeatureCollection", "features": []}
            })
    else:
        print(f"File not found: {json_file}")
        all_districts_data.append({
            "name": district_name,
            "geojson": {"type": "FeatureCollection", "features": []}
        })

# Create the HTML with embedded data
html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kerala Organizational Districts Map</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f5f5;
        }
        #map {
            height: 100vh;
            width: 100%;
            background: #ffffff;
        }
        .info {
            padding: 12px 16px;
            font: 14px/18px Arial, Helvetica, sans-serif;
            background: white;
            background: rgba(255,255,255,0.95);
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            border-radius: 8px;
            min-width: 220px;
        }
        .info h4 {
            margin: 0 0 8px;
            color: #333;
            font-size: 16px;
            border-bottom: 2px solid #3388ff;
            padding-bottom: 6px;
        }
        .info p {
            margin: 5px 0;
            color: #555;
        }
        .legend {
            line-height: 22px;
            color: #555;
            max-height: 400px;
            overflow-y: auto;
        }
        .legend h4 {
            margin-bottom: 10px;
            position: sticky;
            top: 0;
            background: white;
            padding-bottom: 5px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            margin: 3px 0;
            cursor: pointer;
            padding: 3px 6px;
            border-radius: 4px;
            transition: background-color 0.2s;
        }
        .legend-item:hover {
            background-color: #e8f4ff;
        }
        .legend i {
            width: 20px;
            height: 20px;
            margin-right: 10px;
            opacity: 0.85;
            border-radius: 3px;
            flex-shrink: 0;
            border: 1px solid rgba(0,0,0,0.2);
        }
        .legend span {
            font-size: 12px;
        }
        .title-control {
            background: rgba(255,255,255,0.95);
            padding: 14px 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        .title-control h2 {
            margin: 0;
            color: #333;
            font-size: 20px;
        }
        .title-control p {
            margin: 5px 0 0;
            color: #666;
            font-size: 13px;
        }
        /* Hide Leaflet attribution for cleaner look */
        .leaflet-control-attribution {
            display: none;
        }
    </style>
</head>
<body>
    <div id="map"></div>

    <script>
        // Initialize the map centered on Kerala - NO base tiles
        const map = L.map('map', {
            center: [10.5, 76.3],
            zoom: 7,
            zoomControl: true,
            attributionControl: false
        });

        // Color palette for 30 districts - vibrant and distinct colors
        const colors = [
            '#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00',
            '#ffdd33', '#a65628', '#f781bf', '#66c2a5', '#fc8d62',
            '#8da0cb', '#e78ac3', '#a6d854', '#ffd92f', '#e5c494',
            '#1b9e77', '#d95f02', '#7570b3', '#e7298a', '#66a61e',
            '#e6ab02', '#a6761d', '#8dd3c7', '#bebada', '#fb8072',
            '#80b1d3', '#fdb462', '#b3de69', '#fccde5', '#bc80bd'
        ];

        // Info control
        const info = L.control({ position: 'topright' });
        info.onAdd = function(map) {
            this._div = L.DomUtil.create('div', 'info');
            this.update();
            return this._div;
        };
        info.update = function(props) {
            this._div.innerHTML = '<h4>Kerala Organizational Districts</h4>' + 
                (props ? 
                    '<p><strong style="font-size: 15px;">' + props.name + '</strong></p>'
                    : '<p>Hover over a district</p>');
        };
        info.addTo(map);

        // Title control
        const titleControl = L.control({ position: 'topleft' });
        titleControl.onAdd = function(map) {
            const div = L.DomUtil.create('div', 'title-control');
            div.innerHTML = '<h2>🗺️ Kerala Organizational Districts</h2><p>30 Districts</p>';
            return div;
        };
        titleControl.addTo(map);

        // Store layers for legend interaction
        const districtLayers = {};
        let allBounds = null;

        // GeoJSON data for all 30 organizational districts
        const districtsData = ''' + json.dumps(all_districts_data, ensure_ascii=False) + ''';

        // Style function
        function getStyle(index) {
            return {
                fillColor: colors[index % colors.length],
                weight: 2,
                opacity: 1,
                color: '#333',
                fillOpacity: 0.7
            };
        }

        // Highlight style
        function highlightFeature(e) {
            const layer = e.target;
            layer.setStyle({
                weight: 3,
                color: '#000',
                fillOpacity: 0.85
            });
            layer.bringToFront();
            info.update(layer.feature.properties);
        }

        // Reset style
        function resetHighlight(e, index) {
            e.target.setStyle(getStyle(index));
            info.update();
        }

        // Zoom to feature
        function zoomToFeature(e) {
            map.fitBounds(e.target.getBounds(), { padding: [50, 50] });
        }

        // Add each district to the map
        districtsData.forEach((district, index) => {
            if (district.geojson && district.geojson.features && district.geojson.features.length > 0) {
                const layer = L.geoJSON(district.geojson, {
                    style: getStyle(index),
                    onEachFeature: function(feature, layer) {
                        feature.properties = { name: district.name };
                        layer.on({
                            mouseover: highlightFeature,
                            mouseout: (e) => resetHighlight(e, index),
                            click: zoomToFeature
                        });
                    }
                }).addTo(map);
                
                districtLayers[district.name] = { layer: layer, color: colors[index % colors.length] };
                
                if (allBounds === null) {
                    allBounds = layer.getBounds();
                } else {
                    allBounds.extend(layer.getBounds());
                }
            }
        });

        // Fit map to Kerala bounds
        if (allBounds) {
            map.fitBounds(allBounds, { padding: [30, 30] });
        }

        // Legend
        const legend = L.control({ position: 'bottomright' });
        legend.onAdd = function(map) {
            const div = L.DomUtil.create('div', 'info legend');
            div.innerHTML = '<h4>Districts</h4>';
            
            districtsData.forEach((district, index) => {
                if (district.geojson && district.geojson.features && district.geojson.features.length > 0) {
                    const item = document.createElement('div');
                    item.className = 'legend-item';
                    item.innerHTML = '<i style="background:' + colors[index % colors.length] + '"></i><span>' + district.name + '</span>';
                    item.onclick = function() {
                        const layerData = districtLayers[district.name];
                        if (layerData) {
                            map.fitBounds(layerData.layer.getBounds(), { padding: [50, 50] });
                        }
                    };
                    div.appendChild(item);
                }
            });
            
            return div;
        };
        legend.addTo(map);
    </script>
</body>
</html>
'''

# Write the final HTML file
output_path = Path("/Users/varahelap/Downloads/Reults map db/kerala_map_v2.html")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"\n✅ Map generated successfully!")
print(f"📁 Output file: {output_path}")
print(f"📊 Total districts processed: {len(all_districts_data)}")
