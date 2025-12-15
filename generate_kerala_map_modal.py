import json
import csv
from pathlib import Path
from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.validation import make_valid

base_dir = Path("/Users/varahelap/Downloads/Reults map db/kerala_lb_by_org_district")
csv_file = Path("/Users/varahelap/Downloads/Reults map db/Organisational District Wise Result 2025 - 30 Org Panchayat.csv")

districts = [
    "Alappuzha North", "Alappuzha South", "Ernakulam City", "Ernakulam East", "Ernakulam North",
    "Idukki North", "Idukki South", "Kannur North", "Kannur South", "Kasaragod",
    "Kollam East", "Kollam West", "Kottayam East", "Kottayam West", "Kozhikode City",
    "Kozhikode North", "Kozhikode Rural", "Malappuram Central", "Malappuram East", "Malappuram West",
    "Palakkad East", "Palakkad West", "Pathanamthitta", "Thiruvananthapuram City", 
    "Thiruvananthapuram North", "Thiruvananthapuram South", "Thrissur City", "Thrissur North",
    "Thrissur South", "Wayanad"
]

# Load CSV data
district_data = {}
with open(csv_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        org_district = row.get('Org District', '').strip()
        if org_district and org_district != 'Grand Total':
            district_data[org_district] = {
                'totalWards2025': row.get('Total Wards 2025', ''),
                'ndaWards2025': row.get('NDA - 2025 Result Wards', ''),
                'targetWards': row.get('Target Wards', ''),
                'ndaWards2020': row.get('NDA - 2020 Wards', ''),
                'ndaVotes2025': row.get('NDA 2025 Vote', ''),
                'voteShare2025': row.get('2025 Vote Share', ''),
                'targetVoteShare': row.get('Target Vote Share', ''),
                'votes2024': row.get('2024 Votes', ''),
                'voteShare2024': row.get('2024 Vote Share', ''),
                'votes2020': row.get('2020 Votes', ''),
                'voteShare2020': row.get('2020 Vote Share', ''),
            }

print(f"Loaded data for {len(district_data)} districts from CSV")

def extract_all_features(data):
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
    if geometry.geom_type == 'Polygon':
        return Polygon(geometry.exterior)
    elif geometry.geom_type == 'MultiPolygon':
        polygons_without_holes = [Polygon(poly.exterior) for poly in geometry.geoms]
        return MultiPolygon(polygons_without_holes)
    return geometry

def merge_features_to_boundary(features):
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
        except:
            continue
    
    if not polygons:
        return None, None
    
    try:
        expanded_polygons = [poly.buffer(0.012) for poly in polygons]
        merged = unary_union(expanded_polygons)
        merged = merged.buffer(-0.005)
        merged = remove_holes(merged)
        merged = merged.simplify(0.001, preserve_topology=True)
        if not merged.is_valid:
            merged = make_valid(merged)
        if merged.is_empty:
            merged = unary_union(polygons)
            merged = merged.buffer(0.003).buffer(-0.001)
            merged = remove_holes(merged)
        centroid = merged.centroid
        return merged, centroid
    except Exception as e:
        print(f"    Error: {e}")
        return None, None

# Process all districts
all_districts_data = []

for district_name in districts:
    json_file = base_dir / district_name / f"{district_name}_hierarchy_with_geojson.json"
    
    if json_file.exists():
        print(f"Processing: {district_name}")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        features = extract_all_features(data)
        merged_boundary, centroid = merge_features_to_boundary(features)
        
        if merged_boundary and not merged_boundary.is_empty:
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
                "centroid": [centroid.x, centroid.y] if centroid else None,
                "data": district_data.get(district_name, {})
            })
            print(f"  ✓ Done")

# HTML Template with Modal
html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Kerala Organizational Districts Map</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; width: 100%; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f0f0; }
        #map { height: 100%; width: 100%; background: #f0f0f0; }
        
        .info {
            padding: 12px 16px; font: 14px/18px Arial, sans-serif; background: white;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15); border-radius: 10px; min-width: 200px; border-left: 4px solid #667eea;
        }
        .info h4 { margin: 0 0 8px; color: #333; font-size: 15px; font-weight: 600; }
        .info p { margin: 5px 0; color: #555; font-size: 14px; }
        
        .legend { line-height: 20px; color: #555; max-height: 50vh; overflow-y: auto; scrollbar-width: thin; }
        .legend::-webkit-scrollbar { width: 6px; }
        .legend::-webkit-scrollbar-thumb { background: #ccc; border-radius: 3px; }
        .legend h4 { margin-bottom: 10px; position: sticky; top: 0; background: white; padding: 5px 0; border-bottom: 2px solid #667eea; }
        .legend-item { display: flex; align-items: center; margin: 4px 0; cursor: pointer; padding: 4px 8px; border-radius: 6px; transition: all 0.2s ease; }
        .legend-item:hover { background-color: #f0f4ff; transform: translateX(3px); }
        .legend i { width: 18px; height: 18px; margin-right: 10px; border-radius: 4px; flex-shrink: 0; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
        .legend span { font-size: 11px; font-weight: 500; }
        
        .title-control { background: white; padding: 12px 18px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.15); border-left: 4px solid #667eea; }
        .title-control h2 { margin: 0; color: #333; font-size: 16px; font-weight: 600; }
        .title-control p { margin: 4px 0 0; color: #666; font-size: 12px; }
        
        .district-label {
            background: none !important; border: none !important; box-shadow: none !important;
            font-size: 9px; font-weight: 700; color: #1a1a2e;
            text-shadow: 1px 1px 0 #fff, -1px 1px 0 #fff, 1px -1px 0 #fff, -1px -1px 0 #fff, 0 1px 0 #fff, 0 -1px 0 #fff, 1px 0 0 #fff, -1px 0 0 #fff;
            white-space: nowrap; text-align: center; pointer-events: none;
        }
        .leaflet-control-attribution { display: none; }

        /* Modal Styles */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            z-index: 10000;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        .modal-overlay.active { display: flex; opacity: 1; }
        
        .modal {
            background: white;
            width: 100%;
            height: 100%;
            overflow-y: auto;
            position: relative;
            animation: slideUp 0.3s ease;
        }
        
        @keyframes slideUp {
            from { transform: translateY(50px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        
        .modal-header {
            position: sticky;
            top: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 10;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        
        .modal-header h2 {
            font-size: 24px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .modal-header .district-color {
            width: 30px;
            height: 30px;
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }
        
        .close-btn {
            background: rgba(255,255,255,0.2);
            border: none;
            color: white;
            font-size: 28px;
            cursor: pointer;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
        }
        .close-btn:hover { background: rgba(255,255,255,0.3); transform: scale(1.1); }
        
        .modal-content {
            padding: 30px;
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #f8f9ff 0%, #fff 100%);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            border: 1px solid #e8ecf4;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.12);
        }
        
        .stat-card.highlight {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .stat-card.highlight .stat-label { color: rgba(255,255,255,0.8); }
        .stat-card.highlight .stat-value { color: white; }
        
        .stat-card.success {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
        }
        .stat-card.success .stat-label { color: rgba(255,255,255,0.8); }
        .stat-card.success .stat-value { color: white; }
        
        .stat-card.warning {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
        }
        .stat-card.warning .stat-label { color: rgba(255,255,255,0.8); }
        .stat-card.warning .stat-value { color: white; }
        
        .stat-label {
            font-size: 13px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
            font-weight: 600;
        }
        
        .stat-value {
            font-size: 32px;
            font-weight: 700;
            color: #333;
        }
        
        .stat-subtitle {
            font-size: 12px;
            margin-top: 8px;
            opacity: 0.8;
        }
        
        .section-title {
            font-size: 20px;
            color: #333;
            margin: 30px 0 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .comparison-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }
        
        .comparison-table th {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 16px 20px;
            text-align: left;
            font-weight: 600;
            font-size: 14px;
        }
        
        .comparison-table td {
            padding: 16px 20px;
            border-bottom: 1px solid #eee;
            font-size: 15px;
        }
        
        .comparison-table tr:last-child td { border-bottom: none; }
        .comparison-table tr:hover td { background: #f8f9ff; }
        
        .trend-up { color: #10b981; font-weight: 600; }
        .trend-down { color: #ef4444; font-weight: 600; }
        
        .progress-bar {
            height: 10px;
            background: #e5e7eb;
            border-radius: 5px;
            overflow: hidden;
            margin-top: 10px;
        }
        .progress-fill {
            height: 100%;
            border-radius: 5px;
            transition: width 0.5s ease;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .modal-header { padding: 15px 20px; }
            .modal-header h2 { font-size: 18px; }
            .modal-content { padding: 20px; }
            .stat-value { font-size: 24px; }
            .stats-grid { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
            .stat-card { padding: 18px; }
            .comparison-table th, .comparison-table td { padding: 12px 15px; font-size: 13px; }
            
            .title-control { padding: 8px 12px; }
            .title-control h2 { font-size: 14px; }
            .legend { max-height: 40vh; }
            .district-label { font-size: 7px; }
        }
        
        @media (max-width: 480px) {
            .modal-header h2 { font-size: 16px; }
            .close-btn { width: 40px; height: 40px; font-size: 24px; }
            .stats-grid { grid-template-columns: 1fr; }
            .stat-value { font-size: 28px; }
        }
    </style>
</head>
<body>
    <div id="map"></div>
    
    <!-- Modal -->
    <div class="modal-overlay" id="modalOverlay">
        <div class="modal">
            <div class="modal-header">
                <h2>
                    <span class="district-color" id="modalDistrictColor"></span>
                    <span id="modalTitle">District Name</span>
                </h2>
                <button class="close-btn" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-content" id="modalContent">
                <!-- Content will be dynamically inserted -->
            </div>
        </div>
    </div>

    <script>
        const map = L.map('map', { center: [10.5, 76.3], zoom: 7, zoomControl: true, attributionControl: false });

        const colorMapping = {
            'Kasaragod': '#FF6B6B', 'Kannur North': '#4ECDC4', 'Kannur South': '#FFE66D',
            'Wayanad': '#6C5CE7', 'Kozhikode City': '#FF9F43', 'Kozhikode North': '#95E1D3',
            'Kozhikode Rural': '#F38181', 'Malappuram West': '#AA96DA', 'Malappuram Central': '#00D2D3',
            'Malappuram East': '#FCBAD3', 'Palakkad West': '#FF85A1', 'Palakkad East': '#A8D8EA',
            'Thrissur North': '#FFC75F', 'Thrissur City': '#845EC2', 'Thrissur South': '#B8F2E6',
            'Ernakulam North': '#FF6F91', 'Ernakulam City': '#FFC312', 'Ernakulam East': '#17C0EB',
            'Idukki North': '#A3CB38', 'Idukki South': '#FDA7DF', 'Kottayam West': '#12CBC4',
            'Kottayam East': '#F79F1F', 'Alappuzha North': '#D980FA', 'Alappuzha South': '#7BED9F',
            'Pathanamthitta': '#FF4757', 'Kollam East': '#70A1FF', 'Kollam West': '#ECCC68',
            'Thiruvananthapuram North': '#5F27CD', 'Thiruvananthapuram City': '#48DBFB',
            'Thiruvananthapuram South': '#FF9FF3'
        };

        const info = L.control({ position: 'topright' });
        info.onAdd = function(map) {
            this._div = L.DomUtil.create('div', 'info');
            this.update();
            return this._div;
        };
        info.update = function(props) {
            this._div.innerHTML = '<h4>🗺️ Kerala Districts</h4>' + 
                (props ? '<p><strong style="color: ' + (colorMapping[props.name] || '#333') + ';">' + props.name + '</strong></p><p style="font-size:12px; color:#888;">Click for details</p>'
                       : '<p style="color: #888;">Hover over a district</p>');
        };
        info.addTo(map);

        const titleControl = L.control({ position: 'topleft' });
        titleControl.onAdd = function(map) {
            const div = L.DomUtil.create('div', 'title-control');
            div.innerHTML = '<h2>🏛️ Kerala Organizational Districts</h2><p>30 Administrative Divisions | Click for Details</p>';
            return div;
        };
        titleControl.addTo(map);

        const districtLayers = {};
        const labelMarkers = [];
        let allBounds = null;

        const districtsData = ''' + json.dumps(all_districts_data, ensure_ascii=False) + ''';

        function getStyle(districtName) {
            return { fillColor: colorMapping[districtName] || '#ccc', weight: 2, opacity: 1, color: '#ffffff', fillOpacity: 0.9 };
        }

        function highlightFeature(e) {
            e.target.setStyle({ weight: 3, color: '#333', fillOpacity: 1 });
            e.target.bringToFront();
            info.update(e.target.feature.properties);
        }

        function resetHighlight(e, name) {
            e.target.setStyle(getStyle(name));
            info.update();
        }

        // Modal Functions
        function openModal(district) {
            const data = district.data || {};
            const color = colorMapping[district.name] || '#667eea';
            
            document.getElementById('modalDistrictColor').style.background = color;
            document.getElementById('modalTitle').textContent = district.name;
            
            const wardsGrowth = parseInt(data.ndaWards2025) - parseInt(data.ndaWards2020);
            const wardsGrowthClass = wardsGrowth >= 0 ? 'trend-up' : 'trend-down';
            const wardsGrowthSymbol = wardsGrowth >= 0 ? '↑' : '↓';
            
            const voteShare2025 = parseFloat(data.voteShare2025) || 0;
            const targetShare = parseFloat(data.targetVoteShare) || 0;
            const progressPercent = targetShare > 0 ? Math.min((voteShare2025 / targetShare) * 100, 100) : 0;
            
            const ndaWards = parseInt(data.ndaWards2025) || 0;
            const totalWards = parseInt(data.totalWards2025) || 1;
            const wardPercent = (ndaWards / totalWards * 100).toFixed(1);
            
            const content = `
                <div class="stats-grid">
                    <div class="stat-card highlight">
                        <div class="stat-label">Total Wards (2025)</div>
                        <div class="stat-value">${data.totalWards2025 || 'N/A'}</div>
                    </div>
                    <div class="stat-card success">
                        <div class="stat-label">NDA Wards Won (2025)</div>
                        <div class="stat-value">${data.ndaWards2025 || 'N/A'}</div>
                        <div class="stat-subtitle">${wardPercent}% of total wards</div>
                    </div>
                    <div class="stat-card warning">
                        <div class="stat-label">Target Wards</div>
                        <div class="stat-value">${data.targetWards || 'N/A'}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">NDA Wards (2020)</div>
                        <div class="stat-value">${data.ndaWards2020 || 'N/A'}</div>
                        <div class="stat-subtitle ${wardsGrowthClass}">${wardsGrowthSymbol} ${Math.abs(wardsGrowth)} wards since 2020</div>
                    </div>
                </div>
                
                <h3 class="section-title">📊 Vote Share Analysis</h3>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-label">2025 Vote Share</div>
                        <div class="stat-value">${data.voteShare2025 || 'N/A'}</div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${voteShare2025}%; background: linear-gradient(90deg, #667eea, #764ba2);"></div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Target Vote Share</div>
                        <div class="stat-value">${data.targetVoteShare || 'N/A'}%</div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${targetShare}%; background: linear-gradient(90deg, #f093fb, #f5576c);"></div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Progress to Target</div>
                        <div class="stat-value">${progressPercent.toFixed(1)}%</div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${progressPercent}%; background: linear-gradient(90deg, #11998e, #38ef7d);"></div>
                        </div>
                    </div>
                </div>
                
                <h3 class="section-title">🗳️ NDA Votes</h3>
                <div class="stats-grid">
                    <div class="stat-card highlight">
                        <div class="stat-label">NDA Votes 2025</div>
                        <div class="stat-value">${parseInt(data.ndaVotes2025 || 0).toLocaleString()}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Votes 2024</div>
                        <div class="stat-value">${parseInt(data.votes2024 || 0).toLocaleString()}</div>
                        <div class="stat-subtitle">Vote Share: ${data.voteShare2024 || 'N/A'}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Votes 2020</div>
                        <div class="stat-value">${parseInt(data.votes2020 || 0).toLocaleString()}</div>
                        <div class="stat-subtitle">Vote Share: ${data.voteShare2020 || 'N/A'}</div>
                    </div>
                </div>
                
                <h3 class="section-title">📈 Year-over-Year Comparison</h3>
                <table class="comparison-table">
                    <thead>
                        <tr>
                            <th>Metric</th>
                            <th>2020</th>
                            <th>2024</th>
                            <th>2025</th>
                            <th>Target</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><strong>NDA Wards</strong></td>
                            <td>${data.ndaWards2020 || '-'}</td>
                            <td>-</td>
                            <td><strong>${data.ndaWards2025 || '-'}</strong></td>
                            <td>${data.targetWards || '-'}</td>
                        </tr>
                        <tr>
                            <td><strong>Vote Share</strong></td>
                            <td>${data.voteShare2020 || '-'}</td>
                            <td>${data.voteShare2024 || '-'}</td>
                            <td><strong>${data.voteShare2025 || '-'}</strong></td>
                            <td>${data.targetVoteShare || '-'}%</td>
                        </tr>
                        <tr>
                            <td><strong>Total Votes</strong></td>
                            <td>${parseInt(data.votes2020 || 0).toLocaleString()}</td>
                            <td>${parseInt(data.votes2024 || 0).toLocaleString()}</td>
                            <td><strong>${parseInt(data.ndaVotes2025 || 0).toLocaleString()}</strong></td>
                            <td>-</td>
                        </tr>
                    </tbody>
                </table>
            `;
            
            document.getElementById('modalContent').innerHTML = content;
            document.getElementById('modalOverlay').classList.add('active');
            document.body.style.overflow = 'hidden';
        }
        
        function closeModal() {
            document.getElementById('modalOverlay').classList.remove('active');
            document.body.style.overflow = '';
        }
        
        // Close on overlay click
        document.getElementById('modalOverlay').addEventListener('click', function(e) {
            if (e.target === this) closeModal();
        });
        
        // Close on Escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeModal();
        });

        // Add districts to map
        districtsData.forEach((district, index) => {
            if (district.geojson && district.geojson.features && district.geojson.features.length > 0) {
                const layer = L.geoJSON(district.geojson, {
                    style: () => getStyle(district.name),
                    onEachFeature: function(feature, layer) {
                        feature.properties = { name: district.name };
                        layer.on({
                            mouseover: highlightFeature,
                            mouseout: (e) => resetHighlight(e, district.name),
                            click: () => openModal(district)
                        });
                    }
                }).addTo(map);
                
                districtLayers[district.name] = { layer: layer, color: colorMapping[district.name] };
                
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
                
                if (allBounds === null) allBounds = layer.getBounds();
                else allBounds.extend(layer.getBounds());
            }
        });

        if (allBounds) map.fitBounds(allBounds, { padding: [20, 20] });

        map.on('zoomend', function() {
            const zoom = map.getZoom();
            labelMarkers.forEach(marker => {
                const el = marker.getElement();
                if (el) {
                    el.style.fontSize = zoom >= 8 ? '10px' : zoom >= 7 ? '8px' : '7px';
                }
            });
        });

        const legend = L.control({ position: 'bottomright' });
        legend.onAdd = function(map) {
            const div = L.DomUtil.create('div', 'info legend');
            div.innerHTML = '<h4>Districts</h4>';
            [...districtsData].sort((a, b) => a.name.localeCompare(b.name)).forEach((district) => {
                if (district.geojson && district.geojson.features && district.geojson.features.length > 0) {
                    const item = document.createElement('div');
                    item.className = 'legend-item';
                    item.innerHTML = '<i style="background:' + colorMapping[district.name] + '"></i><span>' + district.name + '</span>';
                    item.onclick = () => openModal(district);
                    div.appendChild(item);
                }
            });
            return div;
        };
        legend.addTo(map);

        window.addEventListener('resize', () => map.invalidateSize());
    </script>
</body>
</html>
'''

output_path = Path("/Users/varahelap/Downloads/Reults map db/kerala_map_with_modal.html")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"\n✅ Map with modal generated: {output_path}")
