import json
import os
from pathlib import Path
from shapely.geometry import shape, mapping, Point, Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.validation import make_valid

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

def remove_holes(geometry):
    """Remove all interior holes from a polygon or multipolygon"""
    if geometry.geom_type == 'Polygon':
        # Create new polygon with only exterior ring (no holes)
        return Polygon(geometry.exterior)
    elif geometry.geom_type == 'MultiPolygon':
        # Remove holes from each polygon in the multipolygon
        polygons_without_holes = []
        for poly in geometry.geoms:
            polygons_without_holes.append(Polygon(poly.exterior))
        return MultiPolygon(polygons_without_holes)
    else:
        return geometry

def merge_features_to_boundary(features):
    """Merge all polygon features into a single boundary polygon without holes"""
    polygons = []
    
    for feature in features:
        try:
            geom = feature.get('geometry')
            if geom and geom.get('type') in ['Polygon', 'MultiPolygon']:
                poly = shape(geom)
                if not poly.is_valid:
                    poly = make_valid(poly)
                if poly.is_valid and not poly.is_empty:
                    polygons.append(poly)
        except Exception as e:
            continue
    
    if not polygons:
        return None, None
    
    try:
        # Merge all polygons
        merged = unary_union(polygons)
        
        # Buffer out slightly to merge nearby polygons, then buffer back
        merged = merged.buffer(0.002).buffer(-0.001)
        
        # Remove all holes from the merged polygon
        merged = remove_holes(merged)
        
        # Simplify slightly to smooth edges
        merged = merged.simplify(0.0008, preserve_topology=True)
        
        # Make sure it's valid
        if not merged.is_valid:
            merged = make_valid(merged)
        
        # Get centroid for label placement
        centroid = merged.centroid
        
        return merged, centroid
    except Exception as e:
        print(f"    Error merging: {e}")
        return None, None

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
            
            features = extract_all_features(data)
            print(f"  - Found {len(features)} polygon features")
            
            merged_boundary, centroid = merge_features_to_boundary(features)
            
            if merged_boundary:
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
                    "geojson": merged_geojson,
                    "centroid": [centroid.x, centroid.y] if centroid else None
                })
                print(f"  ✓ Merged successfully (holes removed)")
            else:
                print(f"  ✗ Failed to merge")
                all_districts_data.append({
                    "name": district_name,
                    "geojson": {"type": "FeatureCollection", "features": []},
                    "centroid": None
                })
            
        except Exception as e:
            print(f"  - Error: {e}")
            all_districts_data.append({
                "name": district_name,
                "geojson": {"type": "FeatureCollection", "features": []},
                "centroid": None
            })
    else:
        print(f"File not found: {json_file}")

# Create the HTML
html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Kerala Organizational Districts Map</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        html, body {
            height: 100%;
            width: 100%;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f8f9fa;
        }
        #map {
            height: 100%;
            width: 100%;
            background: #f8f9fa;
        }
        .info {
            padding: 12px 16px;
            font: 14px/18px Arial, Helvetica, sans-serif;
            background: white;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
            border-radius: 10px;
            min-width: 200px;
            border-left: 4px solid #667eea;
        }
        .info h4 {
            margin: 0 0 8px;
            color: #333;
            font-size: 15px;
            font-weight: 600;
        }
        .info p {
            margin: 5px 0;
            color: #555;
            font-size: 14px;
        }
        .legend {
            line-height: 20px;
            color: #555;
            max-height: 50vh;
            overflow-y: auto;
            scrollbar-width: thin;
        }
        .legend::-webkit-scrollbar {
            width: 6px;
        }
        .legend::-webkit-scrollbar-thumb {
            background: #ccc;
            border-radius: 3px;
        }
        .legend h4 {
            margin-bottom: 10px;
            position: sticky;
            top: 0;
            background: white;
            padding: 5px 0;
            border-bottom: 2px solid #667eea;
        }
        .legend-item {
            display: flex;
            align-items: center;
            margin: 4px 0;
            cursor: pointer;
            padding: 4px 8px;
            border-radius: 6px;
            transition: all 0.2s ease;
        }
        .legend-item:hover {
            background-color: #f0f4ff;
            transform: translateX(3px);
        }
        .legend i {
            width: 18px;
            height: 18px;
            margin-right: 10px;
            border-radius: 4px;
            flex-shrink: 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .legend span {
            font-size: 11px;
            font-weight: 500;
        }
        .title-control {
            background: white;
            padding: 12px 18px;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
            border-left: 4px solid #667eea;
        }
        .title-control h2 {
            margin: 0;
            color: #333;
            font-size: 16px;
            font-weight: 600;
        }
        .title-control p {
            margin: 4px 0 0;
            color: #666;
            font-size: 12px;
        }
        .district-label {
            background: none !important;
            border: none !important;
            box-shadow: none !important;
            font-size: 9px;
            font-weight: 700;
            color: #1a1a2e;
            text-shadow: 
                1px 1px 0 #fff,
                -1px 1px 0 #fff,
                1px -1px 0 #fff,
                -1px -1px 0 #fff,
                0 1px 0 #fff,
                0 -1px 0 #fff,
                1px 0 0 #fff,
                -1px 0 0 #fff,
                2px 2px 2px rgba(255,255,255,0.8);
            white-space: nowrap;
            text-align: center;
            pointer-events: none;
        }
        .leaflet-control-attribution {
            display: none;
        }
        
        /* Responsive adjustments */
        @media (max-width: 768px) {
            .title-control {
                padding: 8px 12px;
            }
            .title-control h2 {
                font-size: 14px;
            }
            .title-control p {
                font-size: 10px;
            }
            .info {
                min-width: 150px;
                padding: 8px 12px;
            }
            .info h4 {
                font-size: 13px;
            }
            .legend {
                max-height: 40vh;
            }
            .legend-item {
                padding: 3px 6px;
            }
            .legend i {
                width: 14px;
                height: 14px;
            }
            .legend span {
                font-size: 10px;
            }
            .district-label {
                font-size: 7px;
            }
        }
        
        @media (max-width: 480px) {
            .title-control h2 {
                font-size: 12px;
            }
            .legend {
                max-height: 35vh;
                max-width: 140px;
            }
            .legend span {
                font-size: 9px;
            }
            .district-label {
                font-size: 6px;
            }
        }
    </style>
</head>
<body>
    <div id="map"></div>

    <script>
        // Initialize map
        const map = L.map('map', {
            center: [10.5, 76.3],
            zoom: 7,
            zoomControl: true,
            attributionControl: false
        });

        // Vibrant color palette - designed so adjacent districts have contrasting colors
        const colorMapping = {
            'Kasaragod': '#FF6B6B',
            'Kannur North': '#4ECDC4',
            'Kannur South': '#FFE66D',
            'Wayanad': '#6C5CE7',
            'Kozhikode City': '#FF9F43',
            'Kozhikode North': '#95E1D3',
            'Kozhikode Rural': '#F38181',
            'Malappuram West': '#AA96DA',
            'Malappuram Central': '#00D2D3',
            'Malappuram East': '#FCBAD3',
            'Palakkad West': '#FF85A1',
            'Palakkad East': '#A8D8EA',
            'Thrissur North': '#FFC75F',
            'Thrissur City': '#845EC2',
            'Thrissur South': '#B8F2E6',
            'Ernakulam North': '#FF6F91',
            'Ernakulam City': '#FFC312',
            'Ernakulam East': '#17C0EB',
            'Idukki North': '#A3CB38',
            'Idukki South': '#FDA7DF',
            'Kottayam West': '#12CBC4',
            'Kottayam East': '#F79F1F',
            'Alappuzha North': '#D980FA',
            'Alappuzha South': '#7BED9F',
            'Pathanamthitta': '#FF4757',
            'Kollam East': '#70A1FF',
            'Kollam West': '#ECCC68',
            'Thiruvananthapuram North': '#5F27CD',
            'Thiruvananthapuram City': '#48DBFB',
            'Thiruvananthapuram South': '#FF9FF3'
        };

        // Info control
        const info = L.control({ position: 'topright' });
        info.onAdd = function(map) {
            this._div = L.DomUtil.create('div', 'info');
            this.update();
            return this._div;
        };
        info.update = function(props) {
            this._div.innerHTML = '<h4>🗺️ Kerala Districts</h4>' + 
                (props ? 
                    '<p><strong style="color: ' + (colorMapping[props.name] || '#333') + ';">' + props.name + '</strong></p>'
                    : '<p style="color: #888;">Hover over a district</p>');
        };
        info.addTo(map);

        // Title control
        const titleControl = L.control({ position: 'topleft' });
        titleControl.onAdd = function(map) {
            const div = L.DomUtil.create('div', 'title-control');
            div.innerHTML = '<h2>🏛️ Kerala Organizational Districts</h2><p>30 Administrative Divisions</p>';
            return div;
        };
        titleControl.addTo(map);

        // Store layers
        const districtLayers = {};
        const labelMarkers = [];
        let allBounds = null;

        // District data
        const districtsData = ''' + json.dumps(all_districts_data, ensure_ascii=False) + ''';

        // Style function
        function getStyle(districtName) {
            return {
                fillColor: colorMapping[districtName] || '#ccc',
                weight: 2,
                opacity: 1,
                color: '#ffffff',
                fillOpacity: 0.9
            };
        }

        // Highlight style
        function highlightFeature(e) {
            const layer = e.target;
            layer.setStyle({
                weight: 3,
                color: '#333',
                fillOpacity: 1
            });
            layer.bringToFront();
            info.update(layer.feature.properties);
        }

        // Reset style
        function resetHighlight(e, name) {
            e.target.setStyle(getStyle(name));
            info.update();
        }

        // Zoom to feature
        function zoomToFeature(e) {
            map.fitBounds(e.target.getBounds(), { padding: [50, 50] });
        }

        // Add districts
        districtsData.forEach((district, index) => {
            if (district.geojson && district.geojson.features && district.geojson.features.length > 0) {
                const layer = L.geoJSON(district.geojson, {
                    style: () => getStyle(district.name),
                    onEachFeature: function(feature, layer) {
                        feature.properties = { name: district.name };
                        layer.on({
                            mouseover: highlightFeature,
                            mouseout: (e) => resetHighlight(e, district.name),
                            click: zoomToFeature
                        });
                    }
                }).addTo(map);
                
                districtLayers[district.name] = { layer: layer, color: colorMapping[district.name] };
                
                // Add label at centroid
                if (district.centroid) {
                    const label = L.marker([district.centroid[1], district.centroid[0]], {
                        icon: L.divIcon({
                            className: 'district-label',
                            html: district.name.replace(' ', '<br>'),
                            iconSize: [80, 40],
                            iconAnchor: [40, 20]
                        })
                    }).addTo(map);
                    labelMarkers.push(label);
                }
                
                if (allBounds === null) {
                    allBounds = layer.getBounds();
                } else {
                    allBounds.extend(layer.getBounds());
                }
            }
        });

        // Fit to Kerala
        if (allBounds) {
            map.fitBounds(allBounds, { padding: [20, 20] });
        }

        // Show/hide labels based on zoom
        map.on('zoomend', function() {
            const zoom = map.getZoom();
            labelMarkers.forEach(marker => {
                const el = marker.getElement();
                if (el) {
                    if (zoom >= 8) {
                        el.style.fontSize = '10px';
                        el.style.display = 'block';
                    } else if (zoom >= 7) {
                        el.style.fontSize = '8px';
                        el.style.display = 'block';
                    } else {
                        el.style.fontSize = '7px';
                        el.style.display = 'block';
                    }
                }
            });
        });

        // Legend
        const legend = L.control({ position: 'bottomright' });
        legend.onAdd = function(map) {
            const div = L.DomUtil.create('div', 'info legend');
            div.innerHTML = '<h4>Districts</h4>';
            
            // Sort districts for legend display
            const sortedDistricts = [...districtsData].sort((a, b) => a.name.localeCompare(b.name));
            
            sortedDistricts.forEach((district) => {
                if (district.geojson && district.geojson.features && district.geojson.features.length > 0) {
                    const item = document.createElement('div');
                    item.className = 'legend-item';
                    item.innerHTML = '<i style="background:' + colorMapping[district.name] + '"></i><span>' + district.name + '</span>';
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

        // Handle window resize
        window.addEventListener('resize', function() {
            map.invalidateSize();
        });
    </script>
</body>
</html>
'''

# Write the final HTML file
output_path = Path("/Users/varahelap/Downloads/Reults map db/kerala_map_v4.html")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"\n✅ Map generated successfully!")
print(f"📁 Output file: {output_path}")
print(f"📊 Total districts: {len(all_districts_data)}")
