from django.contrib.gis.geos import Point
from jsonpath_ng import parse

location_expression = parse('$.geometry.coordinates')

def update_station_geometry(station,wmdrv2_data):
    """
    Update the geometry of a Station instance based on the provided WMDv2 data.
    """
    
    location_value = location_expression.find(wmdrv2_data)

    if not location_value or len(location_value) == 0 or (len(location_value[0].value) != 2 and len(location_value[0].value) != 3):
        raise ValueError("Missing required field 'location' in wmdrv2 JSON data")

    x,y = location_value[0].value[0], location_value[0].value[1]
    print(f"Updating station geometry of {station} to Point({x}, {y})")

    station.location = Point(x=x, y=y, srid=4326)
