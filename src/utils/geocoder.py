import ssl
import certifi
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

def get_coordinates(location_name: str) -> tuple:
    """
    Girilen şehir/ilçe ismini koordinatlara çevirir.
    Mac SSL sorununu 'certifi' paketiyle çöz
    """
    ctx = ssl.create_default_context(cafile=certifi.where())

    try:
        locator = Nominatim(user_agent="spatial_route_optimizer", ssl_context=ctx)
        location = locator.geocode(location_name, exactly_one=False, limit=10, timeout=10)

        if location:
            return {loc.address: (loc.latitude, loc.longitude) for loc in location}
        else:
            return {}
        
    except GeocoderTimedOut:
        print("timeout error.")
        return {}