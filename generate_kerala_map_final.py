import json
import csv
from pathlib import Path
from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.validation import make_valid

base_dir = Path("/Users/devandev/Downloads/Reults map db/kerala_lb_by_org_district")
csv_dir = Path("/Users/devandev/Downloads/Reults map db")

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

def extract_local_bodies(data):
    """Extract local body information from the hierarchy"""
    local_bodies = {
        'panchayat': [],
        'municipality': [],
        'corporation': []
    }
    
    if isinstance(data, dict):
        if 'local_bodies' in data and isinstance(data['local_bodies'], list):
            lsgi_type = data.get('lsgi_type', '').upper()
            for lb in data['local_bodies']:
                lb_info = {
                    'name': lb.get('name', ''),
                    'code': lb.get('code', ''),
                    'ward_count': lb.get('ward_count', 0)
                }
                if lsgi_type == 'G':
                    local_bodies['panchayat'].append(lb_info)
                elif lsgi_type == 'M':
                    local_bodies['municipality'].append(lb_info)
                elif lsgi_type == 'C':
                    local_bodies['corporation'].append(lb_info)
        
        for key, value in data.items():
            if key != 'local_bodies':
                nested_lbs = extract_local_bodies(value)
                local_bodies['panchayat'].extend(nested_lbs['panchayat'])
                local_bodies['municipality'].extend(nested_lbs['municipality'])
                local_bodies['corporation'].extend(nested_lbs['corporation'])
    elif isinstance(data, list):
        for item in data:
            nested_lbs = extract_local_bodies(item)
            local_bodies['panchayat'].extend(nested_lbs['panchayat'])
            local_bodies['municipality'].extend(nested_lbs['municipality'])
            local_bodies['corporation'].extend(nested_lbs['corporation'])
    
    return local_bodies

def remove_holes(geometry):
    """Remove all interior holes from a polygon or multipolygon"""
    if geometry.geom_type == 'Polygon':
        return Polygon(geometry.exterior)
    elif geometry.geom_type == 'MultiPolygon':
        polygons_without_holes = [Polygon(poly.exterior) for poly in geometry.geoms]
        return MultiPolygon(polygons_without_holes)
    return geometry

def merge_features_to_boundary(features):
    """Merge all polygon features - expand each to fill gaps from missing local bodies"""
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
        # STEP 1: Buffer each polygon outward significantly
        # This makes adjacent polygons expand and meet where there are gaps
        expanded_polygons = []
        for poly in polygons:
            # Buffer by ~1km (0.01 degrees) to fill gaps from missing local bodies
            expanded = poly.buffer(0.012)
            expanded_polygons.append(expanded)
        
        # STEP 2: Merge all expanded polygons - they will overlap and merge
        merged = unary_union(expanded_polygons)
        
        # STEP 3: Buffer back inward slightly to smooth the edges
        # But not too much - we want to keep the filled gaps
        merged = merged.buffer(-0.005)
        
        # STEP 4: Remove any remaining holes
        merged = remove_holes(merged)
        
        # STEP 5: Simplify to clean up the geometry
        merged = merged.simplify(0.001, preserve_topology=True)
        
        if not merged.is_valid:
            merged = make_valid(merged)
        
        # Handle case where buffer made it empty
        if merged.is_empty:
            # Fallback: just merge without aggressive buffering
            merged = unary_union(polygons)
            merged = merged.buffer(0.003).buffer(-0.001)
            merged = remove_holes(merged)
        
        # Use representative_point instead of centroid so the label
        # is guaranteed to fall inside the polygon (better visual centering)
        label_point = merged.representative_point()
        return merged, label_point
    except Exception as e:
        print(f"    Error: {e}")
        return None, None

# Load all CSV data
csv_files = {
    'org_panchayat_30': 'Organisational District Wise Result 2025 - 30 Org Panchayat (2).csv',
    'corporation': 'Organisational District Wise Result 2025 - Corporation Latest (2).csv',
    'municipality': 'Organisational District Wise Result 2025 - Municipality Latest (2).csv',
    'od_panchayat_first_no_tie': 'Organisational District Wise Result 2025 - OD Panchayat first (No tie) (1).csv',
    'od_panchayat_first_tie': 'Organisational District Wise Result 2025 - OD Panchayat First (Tie) (1).csv',
    'od_panchayat_second_no_tie': 'Organisational District Wise Result 2025 -  OD Panchayat Second (No Tie) (1).csv',
    'od_panchayat_second_tie': 'Organisational District Wise Result 2025 - OD Panchayat Second (Tie) (1).csv',
    'municipality_2nd_no_tie': 'Organisational District Wise Result 2025 - Municipality 2nd (NO TIE) .csv',
    'municipality_2nd_tie': 'Organisational District Wise Result 2025 - M - 2nd (Tie) (2).csv'
}

all_csv_data = {}
for key, filename in csv_files.items():
    csv_path = csv_dir / filename
    if csv_path.exists():
        print(f"Loading: {filename}")
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                org_district = row.get('Org District', '').strip()
                if org_district and org_district != 'Grand Total':
                    if org_district not in all_csv_data:
                        all_csv_data[org_district] = {}
                    all_csv_data[org_district][key] = dict(row)
        print(f"  ✓ Loaded data for {key}")
    else:
        print(f"  ✗ File not found: {filename}")

# Load Result.csv to get counts for each category
result_csv_path = csv_dir / 'Organisational District Wise Result 2025 - Result.csv'
result_data = {}
if result_csv_path.exists():
    print(f"\nLoading: Result.csv")
    with open(result_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            org_district = row.get('Org District', '').strip()
            if org_district and org_district != 'Grand Total':
                result_data[org_district] = {
                    'gp_first_no_tie': row.get('GP First Without Tie', '0').strip() or '0',
                    'gp_first_tie': row.get('GP First Tie', '0').strip() or '0',
                    'gp_second_no_tie': row.get('GP Second Without Tie', '0').strip() or '0',
                    'gp_second_tie': row.get('GP Second Tie', '0').strip() or '0',
                    'municipality_first': row.get('Municipality First ', '0').strip() or '0',
                    'municipality_2nd_no_tie': row.get('Municipality 2nd Without Tie', '0').strip() or '0',
                    'municipality_2nd_tie': row.get('Municipality 2nd With Tie', '0').strip() or '0',
                    'corporation_1st': row.get('Corporation 1st', '0').strip() or '0'
                }
    print(f"  ✓ Loaded Result.csv for {len(result_data)} districts")
else:
    print(f"  ✗ File not found: Result.csv")

# Load Results-2025 - Sheet1.csv for Local Body data
results_2025_path = csv_dir / 'Results-2025 - Sheet1.csv'
results_2025_data = {}
if results_2025_path.exists():
    print(f"\nLoading: Results-2025 - Sheet1.csv")
    with open(results_2025_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
        # Skip header rows (rows 0-1 are headers, data starts from row 2)
        for row in rows[6:]:  # Start from row 6 (index 6) which has actual data
            if len(row) >= 16:
                district = row[0].strip()
                if district and district != 'Total':
                    try:
                        # Column indices based on CSV structure:
                        # 0=District, 1=GP Total No., 4=GP 2020 Won, 5=GP 2025 Target
                        # 6=Municipality Total No., 9=Municipality 2020 Won, 10=Municipality 2025 Target
                        # 11=Corporation Total No., 14=Corporation 2020, 15=Corporation 2025 Target
                        gp_total = row[1].strip() if len(row) > 1 and row[1].strip() and row[1].strip() != '-' else '0'
                        gp_2020_won = row[4].strip() if len(row) > 4 and row[4].strip() and row[4].strip() != '-' else '0'
                        gp_2025_target = row[5].strip() if len(row) > 5 and row[5].strip() and row[5].strip() != '-' else '0'
                        
                        m_total = row[6].strip() if len(row) > 6 and row[6].strip() and row[6].strip() != '-' else '0'
                        m_2020_won = row[9].strip() if len(row) > 9 and row[9].strip() and row[9].strip() != '-' else '0'
                        m_2025_target = row[10].strip() if len(row) > 10 and row[10].strip() and row[10].strip() != '-' else '0'
                        
                        c_total = row[11].strip() if len(row) > 11 and row[11].strip() and row[11].strip() != '-' else '0'
                        c_2020 = row[14].strip() if len(row) > 14 and row[14].strip() and row[14].strip() != '-' else '0'
                        c_2025_target = row[15].strip() if len(row) > 15 and row[15].strip() and row[15].strip() != '-' else '0'
                        
                        results_2025_data[district] = {
                            'gp_total': gp_total,
                            'gp_2020_won': gp_2020_won,
                            'gp_2025_target': gp_2025_target,
                            'm_total': m_total,
                            'm_2020_won': m_2020_won,
                            'm_2025_target': m_2025_target,
                            'c_total': c_total,
                            'c_2020': c_2020,
                            'c_2025_target': c_2025_target
                        }
                    except (IndexError, ValueError) as e:
                        continue
    print(f"  ✓ Loaded Results-2025 - Sheet1.csv for {len(results_2025_data)} districts")
else:
    print(f"  ✗ File not found: Results-2025 - Sheet1.csv")

print(f"\nLoaded CSV data for {len(all_csv_data)} districts\n")

# Process all districts
all_districts_data = []

for district_name in districts:
    json_file = base_dir / district_name / f"{district_name}_hierarchy_with_geojson.json"
    
    if json_file.exists():
        print(f"Processing: {district_name}")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        features = extract_all_features(data)
        local_bodies = extract_local_bodies(data)
        print(f"  - {len(features)} features")
        print(f"  - Local Bodies: {len(local_bodies['panchayat'])} Panchayats, {len(local_bodies['municipality'])} Municipalities, {len(local_bodies['corporation'])} Corporations")
        
        merged_boundary, label_point = merge_features_to_boundary(features)
        
        if merged_boundary and not merged_boundary.is_empty:
            merged_geojson = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {"name": district_name},
                    "geometry": mapping(merged_boundary)
                }]
            }
            # Organize vote share data by local body type
            district_csv = all_csv_data.get(district_name, {})
            district_result = result_data.get(district_name, {})
            
            # Build organized vote share structure
            vote_share_data = {
                "panchayat": {
                    "first_without_tie": {
                        "count": int(district_result.get('gp_first_no_tie', '0') or '0'),
                        "vote_share": None
                    },
                    "first_tie": {
                        "count": int(district_result.get('gp_first_tie', '0') or '0'),
                        "vote_share": None
                    },
                    "second_without_tie": {
                        "count": int(district_result.get('gp_second_no_tie', '0') or '0'),
                        "vote_share": None
                    },
                    "second_tie": {
                        "count": int(district_result.get('gp_second_tie', '0') or '0'),
                        "vote_share": None
                    },
                    "overall": {
                        "vote_share": None
                    }
                },
                "municipality": {
                    "first": {
                        "count": int(district_result.get('municipality_first', '0') or '0'),
                        "vote_share": None
                    },
                    "second_without_tie": {
                        "count": int(district_result.get('municipality_2nd_no_tie', '0') or '0'),
                        "vote_share": None
                    },
                    "second_with_tie": {
                        "count": int(district_result.get('municipality_2nd_tie', '0') or '0'),
                        "vote_share": None
                    },
                    "overall": {
                        "vote_share": None
                    }
                },
                "corporation": {
                    "first": {
                        "count": int(district_result.get('corporation_1st', '0') or '0'),
                        "vote_share": None
                    },
                    "overall": {
                        "vote_share": None
                    }
                }
            }
            
            # Extract vote shares from CSV data
            if district_csv.get('od_panchayat_first_no_tie'):
                d = district_csv['od_panchayat_first_no_tie']
                vote_share_data["panchayat"]["first_without_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            
            if district_csv.get('od_panchayat_first_tie'):
                d = district_csv['od_panchayat_first_tie']
                vote_share_data["panchayat"]["first_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            
            if district_csv.get('od_panchayat_second_no_tie'):
                d = district_csv['od_panchayat_second_no_tie']
                vote_share_data["panchayat"]["second_without_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            
            if district_csv.get('od_panchayat_second_tie'):
                d = district_csv['od_panchayat_second_tie']
                vote_share_data["panchayat"]["second_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            
            if district_csv.get('org_panchayat_30'):
                d = district_csv['org_panchayat_30']
                vote_share_data["panchayat"]["overall"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            
            if district_csv.get('municipality'):
                d = district_csv['municipality']
                vote_share_data["municipality"]["overall"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            
            if district_csv.get('municipality_2nd_no_tie'):
                d = district_csv['municipality_2nd_no_tie']
                vote_share_data["municipality"]["second_without_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            
            if district_csv.get('municipality_2nd_tie'):
                d = district_csv['municipality_2nd_tie']
                vote_share_data["municipality"]["second_with_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            
            if district_csv.get('corporation'):
                d = district_csv['corporation']
                vote_share_data["corporation"]["overall"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
                vote_share_data["corporation"]["first"]["vote_share"] = vote_share_data["corporation"]["overall"]["vote_share"]
            
            # Calculate Local Body Won (First positions: GP First Without Tie + GP First Tie + Municipality First + Corporation 1st)
            local_body_won = (
                int(district_result.get('gp_first_no_tie', '0') or '0') +
                int(district_result.get('gp_first_tie', '0') or '0') +
                int(district_result.get('municipality_first', '0') or '0') +
                int(district_result.get('corporation_1st', '0') or '0')
            )
            
            # Calculate total local bodies won (all categories) for backward compatibility
            total_local_bodies_won = (
                int(district_result.get('gp_first_no_tie', '0') or '0') +
                int(district_result.get('gp_first_tie', '0') or '0') +
                int(district_result.get('gp_second_no_tie', '0') or '0') +
                int(district_result.get('gp_second_tie', '0') or '0') +
                int(district_result.get('municipality_first', '0') or '0') +
                int(district_result.get('municipality_2nd_no_tie', '0') or '0') +
                int(district_result.get('municipality_2nd_tie', '0') or '0') +
                int(district_result.get('corporation_1st', '0') or '0')
            )
            
            # Get data from Results-2025 - Sheet1.csv
            results_2025 = results_2025_data.get(district_name, {})
            target_local_body = (
                int(results_2025.get('gp_2025_target', '0') or '0') +
                int(results_2025.get('m_2025_target', '0') or '0') +
                int(results_2025.get('c_2025_target', '0') or '0')
            )
            total_local_body = (
                int(results_2025.get('gp_total', '0') or '0') +
                int(results_2025.get('m_total', '0') or '0') +
                int(results_2025.get('c_total', '0') or '0')
            )
            lb_2020_won = (
                int(results_2025.get('gp_2020_won', '0') or '0') +
                int(results_2025.get('m_2020_won', '0') or '0') +
                int(results_2025.get('c_2020', '0') or '0')
            )
            
            # Calculate 2nd position Local Body Won
            local_body_2nd_no_tie = (
                int(district_result.get('gp_second_no_tie', '0') or '0') +
                int(district_result.get('municipality_2nd_no_tie', '0') or '0')
            )
            local_body_2nd_with_tie = (
                int(district_result.get('gp_second_tie', '0') or '0') +
                int(district_result.get('municipality_2nd_tie', '0') or '0')
            )
            
            # Calculate 2nd position Ward Won
            od_panchayat_2nd_no_tie = district_csv.get('od_panchayat_second_no_tie', {})
            municipality_2nd_no_tie = district_csv.get('municipality_2nd_no_tie', {})
            ward_2nd_no_tie = (
                int(od_panchayat_2nd_no_tie.get('NDA - 2025 Result Wards', '0').replace(',', '') or '0') +
                int(municipality_2nd_no_tie.get('NDA - 2025 Result Wards', '0').replace(',', '') or '0')
            )
            
            od_panchayat_2nd_tie = district_csv.get('od_panchayat_second_tie', {})
            municipality_2nd_tie = district_csv.get('municipality_2nd_tie', {})
            ward_2nd_with_tie = (
                int(od_panchayat_2nd_tie.get('NDA - 2025 Result Wards', '0').replace(',', '') or '0') +
                int(municipality_2nd_tie.get('NDA - 2025 Result Wards', '0').replace(',', '') or '0')
            )
            
            all_districts_data.append({
                "name": district_name,
                "geojson": merged_geojson,
                # Keep the key name as "centroid" for the frontend,
                # but the value is now an interior label point
                "centroid": [label_point.x, label_point.y] if label_point else None,
                "csvData": district_csv,
                "voteShareData": vote_share_data,
                "totalLocalBodiesWon": total_local_bodies_won,
                "localBodyWon": local_body_won,
                "targetLocalBody": target_local_body,
                "totalLocalBody": total_local_body,
                "lb2020Won": lb_2020_won,
                "localBody2ndNoTie": local_body_2nd_no_tie,
                "localBody2ndWithTie": local_body_2nd_with_tie,
                "ward2ndNoTie": ward_2nd_no_tie,
                "ward2ndWithTie": ward_2nd_with_tie,
                "localBodies": {
                    "panchayat": {
                        "count": len(local_bodies['panchayat']),
                        "list": local_bodies['panchayat']
                    },
                    "municipality": {
                        "count": len(local_bodies['municipality']),
                        "list": local_bodies['municipality']
                    },
                    "corporation": {
                        "count": len(local_bodies['corporation']),
                        "list": local_bodies['corporation']
                    }
                }
            })
            print(f"  ✓ Done (gaps filled)")
        else:
            print(f"  ✗ Failed")
            # Organize vote share data even if no geojson
            district_csv = all_csv_data.get(district_name, {})
            district_result = result_data.get(district_name, {})
            
            vote_share_data = {
                "panchayat": {
                    "first_without_tie": {"count": int(district_result.get('gp_first_no_tie', '0') or '0'), "vote_share": None},
                    "first_tie": {"count": int(district_result.get('gp_first_tie', '0') or '0'), "vote_share": None},
                    "second_without_tie": {"count": int(district_result.get('gp_second_no_tie', '0') or '0'), "vote_share": None},
                    "second_tie": {"count": int(district_result.get('gp_second_tie', '0') or '0'), "vote_share": None},
                    "overall": {"vote_share": None}
                },
                "municipality": {
                    "first": {"count": int(district_result.get('municipality_first', '0') or '0'), "vote_share": None},
                    "second_without_tie": {"count": int(district_result.get('municipality_2nd_no_tie', '0') or '0'), "vote_share": None},
                    "second_with_tie": {"count": int(district_result.get('municipality_2nd_tie', '0') or '0'), "vote_share": None},
                    "overall": {"vote_share": None}
                },
                "corporation": {
                    "first": {"count": int(district_result.get('corporation_1st', '0') or '0'), "vote_share": None},
                    "overall": {"vote_share": None}
                }
            }
            
            # Extract vote shares (same logic as above)
            if district_csv.get('od_panchayat_first_no_tie'):
                d = district_csv['od_panchayat_first_no_tie']
                vote_share_data["panchayat"]["first_without_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            if district_csv.get('od_panchayat_first_tie'):
                d = district_csv['od_panchayat_first_tie']
                vote_share_data["panchayat"]["first_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            if district_csv.get('od_panchayat_second_no_tie'):
                d = district_csv['od_panchayat_second_no_tie']
                vote_share_data["panchayat"]["second_without_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            if district_csv.get('od_panchayat_second_tie'):
                d = district_csv['od_panchayat_second_tie']
                vote_share_data["panchayat"]["second_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            if district_csv.get('org_panchayat_30'):
                d = district_csv['org_panchayat_30']
                vote_share_data["panchayat"]["overall"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            if district_csv.get('municipality'):
                d = district_csv['municipality']
                vote_share_data["municipality"]["overall"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            if district_csv.get('municipality_2nd_no_tie'):
                d = district_csv['municipality_2nd_no_tie']
                vote_share_data["municipality"]["second_without_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            if district_csv.get('municipality_2nd_tie'):
                d = district_csv['municipality_2nd_tie']
                vote_share_data["municipality"]["second_with_tie"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
            if district_csv.get('corporation'):
                d = district_csv['corporation']
                vote_share_data["corporation"]["overall"]["vote_share"] = {
                    "2025": d.get('2025 Vote Share', '').strip() or None,
                    "2024": d.get('2024 Vote Share', '').strip() or None,
                    "2020": d.get('2020 Vote Share', '').strip() or None
                }
                vote_share_data["corporation"]["first"]["vote_share"] = vote_share_data["corporation"]["overall"]["vote_share"]
            
            # Calculate Local Body Won (First positions: GP First Without Tie + GP First Tie + Municipality First + Corporation 1st)
            local_body_won = (
                int(district_result.get('gp_first_no_tie', '0') or '0') +
                int(district_result.get('gp_first_tie', '0') or '0') +
                int(district_result.get('municipality_first', '0') or '0') +
                int(district_result.get('corporation_1st', '0') or '0')
            )
            
            # Calculate total local bodies won (all categories) for backward compatibility
            total_local_bodies_won = (
                int(district_result.get('gp_first_no_tie', '0') or '0') +
                int(district_result.get('gp_first_tie', '0') or '0') +
                int(district_result.get('gp_second_no_tie', '0') or '0') +
                int(district_result.get('gp_second_tie', '0') or '0') +
                int(district_result.get('municipality_first', '0') or '0') +
                int(district_result.get('municipality_2nd_no_tie', '0') or '0') +
                int(district_result.get('municipality_2nd_tie', '0') or '0') +
                int(district_result.get('corporation_1st', '0') or '0')
            )
            
            # Get data from Results-2025 - Sheet1.csv
            results_2025 = results_2025_data.get(district_name, {})
            target_local_body = (
                int(results_2025.get('gp_2025_target', '0') or '0') +
                int(results_2025.get('m_2025_target', '0') or '0') +
                int(results_2025.get('c_2025_target', '0') or '0')
            )
            total_local_body = (
                int(results_2025.get('gp_total', '0') or '0') +
                int(results_2025.get('m_total', '0') or '0') +
                int(results_2025.get('c_total', '0') or '0')
            )
            lb_2020_won = (
                int(results_2025.get('gp_2020_won', '0') or '0') +
                int(results_2025.get('m_2020_won', '0') or '0') +
                int(results_2025.get('c_2020', '0') or '0')
            )
            
            # Calculate 2nd position Local Body Won
            local_body_2nd_no_tie = (
                int(district_result.get('gp_second_no_tie', '0') or '0') +
                int(district_result.get('municipality_2nd_no_tie', '0') or '0')
            )
            local_body_2nd_with_tie = (
                int(district_result.get('gp_second_tie', '0') or '0') +
                int(district_result.get('municipality_2nd_tie', '0') or '0')
            )
            
            # Calculate 2nd position Ward Won
            od_panchayat_2nd_no_tie = district_csv.get('od_panchayat_second_no_tie', {})
            municipality_2nd_no_tie = district_csv.get('municipality_2nd_no_tie', {})
            ward_2nd_no_tie = (
                int(od_panchayat_2nd_no_tie.get('NDA - 2025 Result Wards', '0').replace(',', '') or '0') +
                int(municipality_2nd_no_tie.get('NDA - 2025 Result Wards', '0').replace(',', '') or '0')
            )
            
            od_panchayat_2nd_tie = district_csv.get('od_panchayat_second_tie', {})
            municipality_2nd_tie = district_csv.get('municipality_2nd_tie', {})
            ward_2nd_with_tie = (
                int(od_panchayat_2nd_tie.get('NDA - 2025 Result Wards', '0').replace(',', '') or '0') +
                int(municipality_2nd_tie.get('NDA - 2025 Result Wards', '0').replace(',', '') or '0')
            )
            
            all_districts_data.append({
                "name": district_name,
                "geojson": {"type": "FeatureCollection", "features": []},
                "centroid": None,
                "csvData": district_csv,
                "voteShareData": vote_share_data,
                "totalLocalBodiesWon": total_local_bodies_won,
                "localBodyWon": local_body_won,
                "targetLocalBody": target_local_body,
                "totalLocalBody": total_local_body,
                "lb2020Won": lb_2020_won,
                "localBody2ndNoTie": local_body_2nd_no_tie,
                "localBody2ndWithTie": local_body_2nd_with_tie,
                "ward2ndNoTie": ward_2nd_no_tie,
                "ward2ndWithTie": ward_2nd_with_tie,
                "localBodies": {
                    "panchayat": {"count": 0, "list": []},
                    "municipality": {"count": 0, "list": []},
                    "corporation": {"count": 0, "list": []}
                }
            })

# HTML Template with Modal
html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Mission 2025 Results - Kerala Districts</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { 
            height: 100%; 
            width: 100%; 
            font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            overflow: hidden;
            margin: 0;
            padding: 0;
        }
        
        .page-header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 20px 30px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            border-bottom: 3px solid rgba(102, 126, 234, 0.5);
            z-index: 1000;
            position: relative;
            text-align: center;
        }
        
        .page-header h1 {
            margin: 0;
            color: #ffffff;
            font-size: 28px;
            font-weight: 800;
            letter-spacing: -0.5px;
            text-shadow: 0 2px 8px rgba(0,0,0,0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
        }
        
        .page-header p {
            margin: 8px 0 0;
            color: rgba(255,255,255,0.85);
            font-size: 14px;
            font-weight: 500;
            letter-spacing: 0.3px;
            text-align: center;
        }
        
        #map { 
            height: calc(100% - 100px); 
            width: 100%; 
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        }
        
        .info {
            padding: 16px 20px;
            font: 14px/20px 'Inter', Arial, sans-serif;
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
            box-shadow: 0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.08);
            border-radius: 16px;
            min-width: 220px;
            border: none;
            backdrop-filter: blur(10px);
        }
        .info h4 { 
            margin: 0 0 10px; 
            color: #1a1a2e; 
            font-size: 16px; 
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        .info p { 
            margin: 6px 0; 
            color: #4a5568; 
            font-size: 14px;
            font-weight: 500;
        }
        
        .legend {
            line-height: 22px; 
            color: #2d3748; 
            max-height: 50vh; 
            overflow-y: auto; 
            scrollbar-width: thin;
        }
        .legend::-webkit-scrollbar { width: 8px; }
        .legend::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
        .legend::-webkit-scrollbar-thumb { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            border-radius: 4px; 
        }
        .legend::-webkit-scrollbar-thumb:hover { background: linear-gradient(135deg, #5568d3 0%, #6a3f8f 100%); }
        .legend h4 { 
            margin-bottom: 12px; 
            position: sticky; 
            top: 0; 
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
            padding: 8px 0; 
            border-bottom: 2px solid #667eea;
            font-weight: 700;
            font-size: 14px;
            color: #1a1a2e;
            letter-spacing: -0.3px;
        }
        .legend-item {
            display: flex; 
            align-items: center; 
            margin: 6px 0; 
            cursor: pointer;
            padding: 8px 12px; 
            border-radius: 10px; 
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            background: transparent;
        }
        .legend-item:hover { 
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
            transform: translateX(5px);
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.15);
        }
        .legend i { 
            width: 20px; 
            height: 20px; 
            margin-right: 12px; 
            border-radius: 6px; 
            flex-shrink: 0; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            border: 2px solid rgba(255,255,255,0.8);
        }
        .legend span { 
            font-size: 12px; 
            font-weight: 600;
            color: #2d3748;
            letter-spacing: -0.2px;
        }
        
        
        .district-label {
            background: none !important; 
            border: none !important; 
            box-shadow: none !important;
            font-size: 10px; 
            font-weight: 800; 
            color: #1a1a2e;
            text-shadow: 2px 2px 0 #fff, -2px 2px 0 #fff, 2px -2px 0 #fff, -2px -2px 0 #fff,
                         0 2px 0 #fff, 0 -2px 0 #fff, 2px 0 0 #fff, -2px 0 0 #fff, 
                         3px 3px 6px rgba(0,0,0,0.3);
            white-space: nowrap; 
            text-align: center; 
            pointer-events: none !important;
            letter-spacing: 0.3px;
        }
        
        /* Ensure marker container doesn't intercept clicks */
        .leaflet-marker-icon.district-label,
        .leaflet-marker-icon.district-label * {
            pointer-events: none !important;
            cursor: default !important;
        }
        .leaflet-control-attribution { display: none; }
        
        /* Enhanced map controls */
        .leaflet-control-zoom a {
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
            color: #667eea;
            border: 2px solid rgba(102, 126, 234, 0.2);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        .leaflet-control-zoom a:hover {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-color: transparent;
            transform: scale(1.05);
        }
        
        @media (max-width: 768px) {
            .page-header { padding: 16px 20px; }
            .page-header h1 { font-size: 22px; }
            .page-header p { font-size: 12px; }
            #map { height: calc(100% - 90px); }
            .info { min-width: 180px; padding: 12px 16px; }
            .info h4 { font-size: 14px; }
            .legend { max-height: 40vh; }
            .legend-item { padding: 6px 10px; }
            .legend i { width: 16px; height: 16px; }
            .legend span { font-size: 11px; }
            .district-label { font-size: 8px; }
        }
        @media (max-width: 480px) {
            .page-header { padding: 12px 16px; }
            .page-header h1 { font-size: 18px; }
            .page-header p { font-size: 11px; }
            #map { height: calc(100% - 80px); }
            .legend { max-height: 35vh; max-width: 160px; }
            .legend span { font-size: 10px; }
            .district-label { font-size: 7px; }
        }
        
        /* Modal Styles */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(4px);
            z-index: 10000;
            display: none;
            justify-content: center;
            align-items: center;
            animation: fadeIn 0.3s ease;
        }
        .modal-overlay.active {
            display: flex;
            opacity: 1;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        .modal {
            background: #ffffff;
            border-radius: 20px;
            width: 90%;
            max-width: 900px;
            max-height: 90vh;
            overflow: hidden;
            box-shadow: 0 25px 80px rgba(0,0,0,0.3);
            animation: slideUp 0.4s ease;
            display: flex;
            flex-direction: column;
        }
        
        @keyframes slideUp {
            from {
                transform: translateY(50px);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }
        
        .modal-header {
            padding: 25px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #eee;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
        }
        
        .modal-header h2 {
            font-size: 24px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .district-badge {
            width: 30px;
            height: 30px;
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }
        
        .close-btn {
            width: 40px;
            height: 40px;
            border: none;
            background: rgba(255,255,255,0.2);
            border-radius: 50%;
            cursor: pointer;
            font-size: 1.5rem;
            color: white;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            line-height: 1;
        }
        .close-btn:hover {
            background: rgba(255,255,255,0.3);
            transform: rotate(90deg);
        }
        
        .modal-body {
            padding: 25px 30px;
            overflow-y: auto;
            max-height: calc(90vh - 100px);
        }
        
        .summary-cards {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-bottom: 25px;
        }
        
        .summary-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 16px;
            padding: 20px;
            color: white;
            text-align: center;
            position: relative;
            overflow: hidden;
        }
        
        .summary-card::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -50%;
            width: 100%;
            height: 100%;
            background: rgba(255,255,255,0.1);
            border-radius: 50%;
        }
        
        .summary-card.green {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }
        
        .summary-card.orange {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        
        .summary-card.blue {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        
        .summary-card .value {
            font-size: 36px;
            font-weight: 700;
            margin: 10px 0;
            position: relative;
            z-index: 1;
        }
        
        .summary-card .label {
            font-size: 15px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            opacity: 0.95;
            position: relative;
            z-index: 1;
        }
        
        .summary-card .change {
            font-size: 14px;
            font-weight: 700;
            margin-top: 8px;
            opacity: 0.9;
            position: relative;
            z-index: 1;
        }
        
        .summary-card .target-progress {
            margin-top: 10px;
            position: relative;
            z-index: 1;
        }
        
        .progress-bar-bg {
            height: 6px;
            background: rgba(255,255,255,0.3);
            border-radius: 3px;
            overflow: hidden;
        }
        
        .progress-bar-fill {
            height: 100%;
            background: rgba(255,255,255,0.9);
            border-radius: 3px;
            transition: width 1s ease;
        }
        
        .vote-trend {
            background: #f8f9fa;
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 25px;
        }
        
        .vote-trend > div:first-child {
            font-weight: 600;
            margin-bottom: 15px;
            color: #333;
        }
        
        .trend-row {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .trend-year {
            width: 50px;
            font-weight: 600;
            color: #666;
            font-size: 14px;
        }
        
        .trend-bar-container {
            flex: 1;
            height: 28px;
            background: #e0e0e0;
            border-radius: 14px;
            overflow: hidden;
            margin: 0 15px;
        }
        
        .trend-bar {
            height: 100%;
            border-radius: 14px;
            transition: width 1s ease;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 10px;
            font-size: 0.75rem;
            font-weight: 600;
            color: white;
        }
        
        .trend-bar.y2020 {
            background: linear-gradient(90deg, #667eea, #764ba2);
        }
        
        .trend-bar.y2024 {
            background: linear-gradient(90deg, #f093fb, #f5576c);
        }
        
        .trend-bar.y2025 {
            background: linear-gradient(90deg, #11998e, #38ef7d);
        }
        
        .trend-votes {
            width: 120px;
            text-align: right;
            font-size: 12px;
            color: #666;
        }
        
        .lb-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 25px;
        }
        
        .lb-card {
            background: white;
            border: 2px solid #eee;
            border-radius: 16px;
            padding: 20px;
            transition: all 0.3s;
        }
        
        .lb-card:hover {
            border-color: #667eea;
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.15);
        }
        
        .lb-card-title {
            font-weight: 600;
            margin-bottom: 10px;
            color: #333;
        }
        
        .lb-card-value {
            font-size: 24px;
            font-weight: 700;
            color: #667eea;
            margin-bottom: 5px;
        }
        
        .lb-card-label {
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }
        
        .lb-card-subvalue {
            font-size: 11px;
            color: #888;
            margin-top: 5px;
        }
        
        .section-title {
            font-size: 20px;
            color: #333;
            margin: 30px 0 15px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .data-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        
        .data-table th {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 15px;
            text-align: left;
            font-weight: 600;
            font-size: 13px;
        }
        
        .data-table td {
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
            font-size: 14px;
        }
        
        .data-table tr:last-child td { border-bottom: none; }
        .data-table tr:hover td { background: #f8f9ff; }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        
        .tab-btn {
            padding: 10px 20px;
            border: none;
            background: #f0f0f0;
            border-radius: 25px;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 14px;
            font-weight: 600;
            color: #666;
        }
        
        .tab-btn.active {
            background: #1a1a2e;
            color: white;
        }
        
        .tab-btn:hover {
            background: #667eea;
            color: white;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .no-data {
            text-align: center;
            padding: 40px;
            color: #999;
            font-style: italic;
        }
        
        /* Vote Share Display Styles */
        .vote-share-category {
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 12px;
            border-left: 4px solid #667eea;
        }
        .vote-share-category h4 {
            margin: 0 0 15px 0;
            color: #1a1a2e;
            font-size: 16px;
            font-weight: 700;
        }
        .vote-share-item {
            background: white;
            padding: 12px 15px;
            margin: 8px 0;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
            transition: all 0.2s ease;
        }
        .vote-share-item:hover {
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.15);
            transform: translateX(3px);
        }
        .vote-share-item.overall {
            background: linear-gradient(135deg, #f0f4ff 0%, #e8edff 100%);
            border-color: #667eea;
            font-weight: 600;
        }
        .vote-share-item strong {
            display: block;
            color: #1a1a2e;
            font-size: 14px;
            margin-bottom: 8px;
        }
        .vote-share-values {
            color: #4a5568;
            font-size: 13px;
            font-family: 'Courier New', monospace;
            padding: 8px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        
        @media (max-width: 768px) {
            .modal { width: 95%; max-height: 95vh; }
            .modal-header { padding: 15px 20px; }
            .modal-header h2 { font-size: 18px; }
            .modal-body { padding: 20px; }
            .summary-cards { grid-template-columns: repeat(2, 1fr); }
            .summary-card .value { font-size: 28px; font-weight: 700; }
            .summary-card .label { font-size: 13px; font-weight: 700; }
            .summary-card .change { font-size: 12px; font-weight: 700; }
            .lb-grid { grid-template-columns: 1fr; }
            .data-table th, .data-table td { padding: 10px 12px; font-size: 12px; }
            .tabs { flex-wrap: wrap; }
            .tab-btn { padding: 8px 15px; font-size: 12px; }
        }
        
        @media (max-width: 480px) {
            .summary-cards { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <header class="page-header">
        <h1>🎯 Mission 2025 Results</h1>
        <p>Kerala Organizational Districts</p>
    </header>
    <div id="map"></div>
    
    <!-- Modal -->
    <div class="modal-overlay" id="modalOverlay">
        <div class="modal">
            <div class="modal-header">
                <h2>
                    <span class="district-badge" id="modalBadge"></span>
                    <span id="modalTitle">District Name</span>
                </h2>
                <button class="close-btn" onclick="closeModal()">×</button>
            </div>
            <div class="modal-body" id="modalBody">
                <!-- Content will be dynamically inserted -->
            </div>
        </div>
    </div>

    <script>
        // Ensure map container exists and has dimensions
        const mapEl = document.getElementById('map');
        if (mapEl) {
            if (mapEl.offsetHeight === 0) {
                mapEl.style.height = window.innerHeight + 'px';
            }
            if (mapEl.offsetWidth === 0) {
                mapEl.style.width = window.innerWidth + 'px';
            }
        }
        
        // Initialize map
        const map = L.map('map', { 
            center: [10.5, 76.3], 
            zoom: 7, 
            zoomControl: true, 
            attributionControl: false 
        });

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
        }

        function resetHighlight(e, name) {
            e.target.setStyle(getStyle(name));
        }

        function formatNumber(num) {
            if (!num || num === 'N/A' || num === 'NA' || num === '') return '-';
            const numStr = String(num).replace(/,/g, '');
            const parsed = parseInt(numStr);
            if (isNaN(parsed)) return num;
            return parsed.toLocaleString();
        }

        function formatPercent(val) {
            if (!val || val === 'N/A' || val === 'NA' || val === '') return '0';
            const cleaned = String(val).replace('%', '').trim();
            const parsed = parseFloat(cleaned);
            if (isNaN(parsed)) return '0';
            return parsed.toFixed(2);
        }

        function getChangeIndicator(current, previous) {
            const curr = parseFloat(current) || 0;
            const prev = parseFloat(previous) || 0;
            const diff = curr - prev;
            if (diff > 0) return `<span style="color: #38ef7d;">↑ +${diff.toFixed(2)}%</span>`;
            if (diff < 0) return `<span style="color: #f5576c;">↓ ${diff.toFixed(2)}%</span>`;
            return '<span style="color: #888;">→ 0%</span>';
        }

        function openModal(district) {
            const data = district.csvData || {};
            const color = colorMapping[district.name] || '#667eea';
            
            document.getElementById('modalBadge').style.background = color;
            document.getElementById('modalTitle').textContent = district.name + ' - Election Results 2025';
            
            // Get data from different sources
            const pData = data.org_panchayat_30 || {};
            const mData = data.municipality || {};
            const cData = data.corporation || {};
            
            // Calculate Set 1: Local Bodies metrics
            const localBodyWon = district.localBodyWon || 0;
            const targetLocalBody = district.targetLocalBody || 0;
            const totalLocalBody = district.totalLocalBody || 0;
            const lb2020Won = district.lb2020Won || 0;
            
            // Calculate Set 2: Wards metrics (sum across all 3 sheets)
            const pWards2025 = parseInt(formatNumber(pData['NDA - 2025 Result Wards']).replace(/,/g, '')) || 0;
            const mWards2025 = parseInt(formatNumber(mData['NDA - 2025 Result Wards']).replace(/,/g, '')) || 0;
            const cWards2025 = parseInt(formatNumber(cData['NDA - 2025 Result Wards']).replace(/,/g, '')) || 0;
            const wardWon = pWards2025 + mWards2025 + cWards2025;
            
            const pTargetWards = parseInt(formatNumber(pData['Target Wards']).replace(/,/g, '')) || 0;
            const mTargetWards = parseInt(formatNumber(mData['Target Wards']).replace(/,/g, '')) || 0;
            const cTargetWards = parseInt(formatNumber(cData['Target Wards']).replace(/,/g, '')) || 0;
            const targetWards = pTargetWards + mTargetWards + cTargetWards;
            
            const pTotalWards = parseInt(formatNumber(pData['Total Wards 2025']).replace(/,/g, '')) || 0;
            const mTotalWards = parseInt(formatNumber(mData['Total Wards 2025']).replace(/,/g, '')) || 0;
            const cTotalWards = parseInt(formatNumber(cData['Total Wards 2025']).replace(/,/g, '')) || 0;
            const totalWards = pTotalWards + mTotalWards + cTotalWards;
            
            const pWards2020 = parseInt(formatNumber(pData['NDA - 2020 Wards']).replace(/,/g, '')) || 0;
            const mWards2020 = parseInt(formatNumber(mData['NDA - 2020 Wards']).replace(/,/g, '')) || 0;
            const cWards2020 = parseInt(formatNumber(cData['NDA - 2020 Wards']).replace(/,/g, '')) || 0;
            const wards2020Won = pWards2020 + mWards2020 + cWards2020;
            
            const wardChange = wardWon - wards2020Won;
            
            // Build summary cards - 8 boxes in 2 sets
            const summaryCards = `
                <div style="margin-bottom: 25px;">
                    <h3 style="color: #667eea; font-size: 16px; font-weight: 700; margin-bottom: 15px;">Local body</h3>
                    <div class="summary-cards">
                        <div class="summary-card" style="background: linear-gradient(135deg, #d299c2 0%, #fef9d7 100%); color: #333;">
                            <div class="value">${localBodyWon}</div>
                            <div class="label">Local Body Won</div>
                            <div class="change">GP First + Municipality First + Corporation 1st</div>
                        </div>
                        <div class="summary-card" style="background: linear-gradient(135deg, #a8e6cf 0%, #88d8a3 100%);">
                            <div class="value">${targetLocalBody}</div>
                            <div class="label">Target Local Body</div>
                            <div class="change">2025 Target</div>
                        </div>
                        <div class="summary-card" style="background: linear-gradient(135deg, #89f7fe 0%, #66a6ff 100%);">
                            <div class="value">${totalLocalBody}</div>
                            <div class="label">Total Local Body</div>
                            <div class="change">All Local Bodies</div>
                        </div>
                        <div class="summary-card" style="background: linear-gradient(135deg, #fad0c4 0%, #ffd1ff 100%); color: #333;">
                            <div class="value">${lb2020Won}</div>
                            <div class="label">2020 LB Won</div>
                            <div class="change">2020 Won</div>
                        </div>
                    </div>
                </div>
                <div style="margin-bottom: 25px;">
                    <h3 style="color: #667eea; font-size: 16px; font-weight: 700; margin-bottom: 15px;">Wards</h3>
                    <div class="summary-cards">
                        <div class="summary-card">
                            <div class="value">${wardWon}</div>
                            <div class="label">Ward Won 2025</div>
                            <div class="change">${wardChange >= 0 ? '↑' : '↓'} ${Math.abs(wardChange)} vs 2020</div>
                        </div>
                        <div class="summary-card green">
                            <div class="value">${targetWards}</div>
                            <div class="label">Target Wards</div>
                            <div class="change">Sum of Target Wards</div>
                        </div>
                        <div class="summary-card orange">
                            <div class="value">${totalWards.toLocaleString()}</div>
                            <div class="label">Total Wards</div>
                            <div class="change">Sum of Total Wards 2025</div>
                        </div>
                        <div class="summary-card blue">
                            <div class="value">${wards2020Won}</div>
                            <div class="label">2020 Wards Won</div>
                            <div class="change">Sum of NDA - 2020 Wards</div>
                        </div>
                    </div>
                </div>
            `;
            
            // Calculate aggregated vote share trend
            const pVote2020 = parseFloat(formatPercent(pData['2020 Vote Share'])) || 0;
            const pVote2024 = parseFloat(formatPercent(pData['2024 Vote Share'])) || 0;
            const pVote2025 = parseFloat(formatPercent(pData['2025 Vote Share'])) || 0;
            const pVotes2020 = parseInt(formatNumber(pData['2020 Votes']).replace(/,/g, '')) || 0;
            const pVotes2024 = parseInt(formatNumber(pData['2024 Votes']).replace(/,/g, '')) || 0;
            const pVotes2025 = parseInt(formatNumber(pData['NDA 2025 Vote']).replace(/,/g, '')) || 0;
            
            const mVote2020 = parseFloat(formatPercent(mData['2020 Vote Share'])) || 0;
            const mVote2024 = parseFloat(formatPercent(mData['2024 Vote Share'])) || 0;
            const mVote2025 = parseFloat(formatPercent(mData['2025 Vote Share'])) || 0;
            const mVotes2020 = parseInt(formatNumber(mData['2020 Votes']).replace(/,/g, '')) || 0;
            const mVotes2024 = parseInt(formatNumber(mData['2024 Votes']).replace(/,/g, '')) || 0;
            const mVotes2025 = parseInt(formatNumber(mData['NDA 2025 Vote']).replace(/,/g, '')) || 0;
            
            const cVote2020 = parseFloat(formatPercent(cData['2020 Vote Share'])) || 0;
            const cVote2024 = parseFloat(formatPercent(cData['2024 Vote Share'])) || 0;
            const cVote2025 = parseFloat(formatPercent(cData['2025 Vote Share'])) || 0;
            const cVotes2020 = parseInt(formatNumber(cData['2020 Votes']).replace(/,/g, '')) || 0;
            const cVotes2024 = parseInt(formatNumber(cData['2024 Votes']).replace(/,/g, '')) || 0;
            const cVotes2025 = parseInt(formatNumber(cData['NDA 2025 Vote']).replace(/,/g, '')) || 0;
            
            // Calculate weighted averages
            const totalVotes2020 = pVotes2020 + mVotes2020 + cVotes2020;
            const totalVotes2024 = pVotes2024 + mVotes2024 + cVotes2024;
            const totalVotes2025 = pVotes2025 + mVotes2025 + cVotes2025;
            
            const avgVoteShare2020 = totalVotes2020 > 0 ? 
                ((pVote2020 * pVotes2020 + mVote2020 * mVotes2020 + cVote2020 * cVotes2020) / totalVotes2020) : 0;
            const avgVoteShare2024 = totalVotes2024 > 0 ? 
                ((pVote2024 * pVotes2024 + mVote2024 * mVotes2024 + cVote2024 * cVotes2024) / totalVotes2024) : 0;
            const avgVoteShare2025 = totalVotes2025 > 0 ? 
                ((pVote2025 * pVotes2025 + mVote2025 * mVotes2025 + cVote2025 * cVotes2025) / totalVotes2025) : 0;
            
            // Vote share trend
            const voteTrend = `
                <div class="vote-trend">
                    <div>Vote Share</div>
                    <div class="trend-row">
                        <div class="trend-year">2020</div>
                        <div class="trend-bar-container">
                            <div class="trend-bar y2020" style="width: ${Math.min(avgVoteShare2020 * 2, 100)}%">
                                ${avgVoteShare2020.toFixed(2)}%
                            </div>
                        </div>
                        <div class="trend-votes">${formatNumber(totalVotes2020)} votes</div>
                    </div>
                    <div class="trend-row">
                        <div class="trend-year">2024</div>
                        <div class="trend-bar-container">
                            <div class="trend-bar y2024" style="width: ${Math.min(avgVoteShare2024 * 2, 100)}%">
                                ${avgVoteShare2024.toFixed(2)}%
                            </div>
                        </div>
                        <div class="trend-votes">${formatNumber(totalVotes2024)} votes</div>
                    </div>
                    <div class="trend-row">
                        <div class="trend-year">2025</div>
                        <div class="trend-bar-container">
                            <div class="trend-bar y2025" style="width: ${Math.min(avgVoteShare2025 * 2, 100)}%">
                                ${avgVoteShare2025.toFixed(2)}%
                            </div>
                        </div>
                        <div class="trend-votes">${formatNumber(totalVotes2025)} votes</div>
                    </div>
                </div>
            `;
            
            // Get 2nd position data
            const localBody2ndNoTie = district.localBody2ndNoTie || 0;
            const localBody2ndWithTie = district.localBody2ndWithTie || 0;
            const ward2ndNoTie = district.ward2ndNoTie || 0;
            const ward2ndWithTie = district.ward2ndWithTie || 0;
            
            // Build Section 3: 2nd Position (2 boxes - Local Body only)
            const secondPositionSection = `
                <div style="margin-bottom: 25px;">
                    <h3 style="color: #667eea; font-size: 16px; font-weight: 700; margin-bottom: 15px;">2nd Position</h3>
                    <div class="summary-cards" style="grid-template-columns: repeat(2, 1fr); max-width: 600px; margin: 0 auto;">
                        <div class="summary-card" style="background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); color: #333;">
                            <div class="value">${localBody2ndNoTie}</div>
                            <div class="label">Local Body Won (2nd)</div>
                            <div class="change">Without Tie</div>
                        </div>
                        <div class="summary-card" style="background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%); color: #333;">
                            <div class="value">${localBody2ndWithTie}</div>
                            <div class="label">Local Body Won (2nd)</div>
                            <div class="change">With Tie</div>
                        </div>
                    </div>
                </div>
            `;
            
            document.getElementById('modalBody').innerHTML = summaryCards + voteTrend + secondPositionSection;
            document.getElementById('modalOverlay').classList.add('active');
            document.body.style.overflow = 'hidden';
        }
        
        function switchTab(tabKey) {
            // Remove active from all tabs and contents
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            // Add active to selected
            const tabBtn = document.querySelector(`[onclick*="${tabKey}"]`);
            const tabContent = document.getElementById('tab_' + tabKey);
            
            if (tabBtn) tabBtn.classList.add('active');
            if (tabContent) tabContent.classList.add('active');
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
                        }),
                        interactive: false
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
                    el.style.display = 'block';
                }
            });
        });

        window.addEventListener('resize', () => map.invalidateSize());
    </script>
</body>
</html>
'''

output_path = Path("/Users/devandev/Downloads/Reults map db/kerala_map_final.html")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"\n✅ Map generated: {output_path}")
