"""
ImmobilienScout24 URL Builder Module
Handles URL construction for apartment searches with Berlin Viertel integration
"""

from urllib.parse import urlencode
from typing import Dict, List, Optional, Tuple, Any
import json


class ImmobilienScout24URLBuilder:
    def __init__(self):
        self.base_url = 'https://www.immobilienscout24.de/Suche/radius/wohnung-mieten'
        
        # Common Berlin Viertel to PLZ mapping for quick lookup
        self.viertel_plz_map = {
            'mitte': ['10115', '10117', '10119', '10178', '10179', '10435', '10559'],
            'charlottenburg': ['10585', '10587', '10625', '10627', '10629', '14057', '14059'],
            'kreuzberg': ['10961', '10963', '10965', '10967', '10969', '10997', '10999'],
            'prenzlauer berg': ['10405', '10407', '10409', '10435', '10437', '10439'],
            'friedrichshain': ['10243', '10245', '10247', '10249'],
            'neukölln': ['12043', '12045', '12047', '12049', '12051', '12053', '12055', '12057', '12059'],
            'schöneberg': ['10777', '10779', '10781', '10783', '10785', '10787', '10823', '10825', '10827', '10829'],
            'wilmersdorf': ['10707', '10709', '10711', '10713', '10715', '10717', '10719', '14193', '14195', '14197', '14199'],
            'tiergarten': ['10553', '10555', '10557', '10559', '10785', '10787'],
            'wedding': ['13347', '13349', '13351', '13353', '13355', '13357', '13359'],
            'moabit': ['10551', '10553', '10555', '10557', '10559'],
            'pankow': ['13187', '13189', '13156', '13158', '13159'],
            'weißensee': ['13086', '13088', '13089'],
            'lichtenberg': ['10315', '10317', '10318', '10319', '13055', '13057', '13059'],
            'tempelhof': ['12101', '12103', '12105', '12107', '12109'],
            'steglitz': ['12163', '12165', '12167', '12169', '12205', '12207', '12209'],
            'spandau': ['13581', '13583', '13585', '13587', '13589', '13591', '13593', '13595', '13597', '13599']
        }

    def build_url(self, search_data: Dict[str, Any]) -> str:
        """
        Build complete ImmobilienScout24 URL with all parameters
        """
        viertel = search_data.get('viertel')
        plz_list = search_data.get('plz_list', [])
        coordinates = search_data.get('coordinates')
        radius = search_data.get('radius')
        budget = search_data.get('budget')
        space = search_data.get('space')
        rooms = search_data.get('rooms')
        floors = search_data.get('floors')
        extras = search_data.get('extras', {})

        params = {}

        # Location parameters
        self._add_location_params(params, viertel, plz_list, coordinates, radius)
        
        # Property parameters
        self._add_property_params(params, budget, space, rooms, floors)
        
        # Equipment and preferences
        self._add_equipment_params(params, extras)
        
        # Meta parameters
        self._add_meta_params(params)

        return f"{self.base_url}?{urlencode(params)}"

    def _add_location_params(self, params: Dict, viertel: Optional[str], 
                           plz_list: List[str], coordinates: Optional[Dict], 
                           radius: Optional[float]):
        """Add location-based parameters"""
        # Center of search address with Viertel context
        if viertel and plz_list:
            params['centerofsearchaddress'] = f"Berlin;;;;;{viertel} ({plz_list[0]});"
        else:
            params['centerofsearchaddress'] = 'Berlin;;;;;Custom Location;'

        # Geocoordinates with radius
        if coordinates and radius:
            params['geocoordinates'] = f"{coordinates['lat']};{coordinates['lon']};{radius}"

        # PLZ filter (if we have specific postal codes for the Viertel)
        if plz_list:
            # ImmobilienScout24 sometimes uses PLZ in the search
            # We can add this as additional context
            params['locationids'] = ','.join(plz_list)

    def _add_property_params(self, params: Dict, budget: Optional[Dict], 
                           space: Optional[Dict], rooms: Optional[Dict], 
                           floors: Optional[Dict]):
        """Add property-related parameters"""
        # Budget
        if budget and budget.get('min') and budget.get('max'):
            params['price'] = f"{budget['min']}-{budget['max']}"
            params['pricetype'] = 'rentpermonth'

        # Living space
        if space and space.get('min') and space.get('max'):
            params['livingspace'] = f"{space['min']}-{space['max']}"

        # Number of rooms
        if rooms and rooms.get('min') and rooms.get('max'):
            params['numberofrooms'] = f"{rooms['min']}-{rooms['max']}"

        # Floor preference
        if floors and floors.get('min') is not None and floors.get('max') is not None:
            params['floor'] = f"{floors['min']}-{floors['max']}"

    def _add_equipment_params(self, params: Dict, extras: Dict):
        """Add equipment and feature parameters"""
        if not extras:
            return

        # Collect equipment features
        equipment = []
        if extras.get('garden'):
            equipment.append('garden')
        if extras.get('balcony'):
            equipment.append('balcony')
        if extras.get('cellar'):
            equipment.append('cellar')
        
        if equipment:
            params['equipment'] = ','.join(equipment)

        # Pet policy
        if extras.get('pets'):
            params['petsallowedtypes'] = 'yes'

        # Exclusion criteria
        if extras.get('no_swaps'):
            params['exclusioncriteria'] = 'swapflat'

        # Promotion filtering
        if extras.get('hide_promoted'):
            params['haspromotion'] = 'false'

    def _add_meta_params(self, params: Dict):
        """Add metadata parameters"""
        params['enteredFrom'] = 'telegram_bot_viertel'

    def get_plz_for_viertel(self, viertel_name: str) -> List[str]:
        """Get PLZ list for a given Viertel (fallback for search failures)"""
        normalized = viertel_name.lower().strip()
        return self.viertel_plz_map.get(normalized, [])

    def validate_search_data(self, search_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate search data completeness"""
        errors = []

        coordinates = search_data.get('coordinates')
        if not coordinates or not coordinates.get('lat') or not coordinates.get('lon'):
            errors.append('Missing coordinates')

        radius = search_data.get('radius')
        if not radius or radius <= 0:
            errors.append('Missing or invalid radius')

        budget = search_data.get('budget')
        if not budget or not budget.get('min') or not budget.get('max'):
            errors.append('Missing budget information')

        space = search_data.get('space')
        if not space or not space.get('min') or not space.get('max'):
            errors.append('Missing space information')

        rooms = search_data.get('rooms')
        if not rooms or not rooms.get('min') or not rooms.get('max'):
            errors.append('Missing rooms information')

        return len(errors) == 0, errors

    def create_search_summary(self, search_data: Dict[str, Any]) -> str:
        """Create a readable summary of the search parameters"""
        viertel = search_data.get('viertel')
        plz_list = search_data.get('plz_list', [])
        radius = search_data.get('radius')
        budget = search_data.get('budget', {})
        space = search_data.get('space', {})
        rooms = search_data.get('rooms', {})
        floors = search_data.get('floors')
        extras = search_data.get('extras', {})

        summary = '📋 **Search Summary:**\n\n'

        # Location
        if viertel:
            summary += f'🏘️ **Neighborhood:** {viertel}'
            if plz_list:
                plz_display = ', '.join(plz_list[:3])
                if len(plz_list) > 3:
                    plz_display += '...'
                summary += f' (PLZ: {plz_display})'
            summary += '\n'
        
        summary += f'📍 **Radius:** {radius} km\n'

        # Property details
        summary += f'💶 **Budget:** €{budget.get("min")}-{budget.get("max")}/month\n'
        summary += f'🏠 **Size:** {space.get("min")}-{space.get("max")} m², {rooms.get("min")}-{rooms.get("max")} rooms\n'
        
        if floors:
            summary += f'🏢 **Floors:** {floors.get("min")}-{floors.get("max")}\n'
        else:
            summary += '🏢 **Floors:** Any\n'

        # Extras
        if extras:
            features = []
            if extras.get('garden'):
                features.append('Garden')
            if extras.get('balcony'):
                features.append('Balcony')
            if extras.get('cellar'):
                features.append('Cellar')
            if extras.get('pets'):
                features.append('Pets allowed')
            if extras.get('no_swaps'):
                features.append('No swaps')
            if extras.get('hide_promoted'):
                features.append('Hide promoted')

            if features:
                summary += f'⚙️ **Features:** {", ".join(features)}\n'

        return summary

    def generate_alternative_urls(self, search_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate alternative search URLs with relaxed criteria"""
        alternatives = []

        # Wider radius
        current_radius = search_data.get('radius', 0)
        if current_radius < 5:
            wider_search = search_data.copy()
            wider_search['radius'] = current_radius + 2
            alternatives.append({
                'title': f'🎯 Expand to {wider_search["radius"]}km radius',
                'url': self.build_url(wider_search)
            })

        # Higher budget range
        budget = search_data.get('budget', {})
        if budget.get('max'):
            higher_budget = search_data.copy()
            higher_budget['budget'] = {
                'min': budget.get('min', 800),
                'max': int(budget.get('max', 1500) * 1.3)
            }
            alternatives.append({
                'title': f'💰 Higher budget (up to €{higher_budget["budget"]["max"]})',
                'url': self.build_url(higher_budget)
            })

        # More flexible space
        space = search_data.get('space', {})
        if space.get('min') and space.get('max'):
            flex_space = search_data.copy()
            flex_space['space'] = {
                'min': max(20, space.get('min', 42) - 10),
                'max': space.get('max', 68) + 15
            }
            alternatives.append({
                'title': f'📐 Flexible size ({flex_space["space"]["min"]}-{flex_space["space"]["max"]}m²)',
                'url': self.build_url(flex_space)
            })

        return alternatives

    def get_viertel_suggestions(self) -> List[str]:
        """Get list of popular Berlin Viertels"""
        return [
            'Mitte', 'Charlottenburg', 'Kreuzberg', 'Prenzlauer Berg',
            'Friedrichshain', 'Neukölln', 'Schöneberg', 'Wilmersdorf',
            'Tiergarten', 'Wedding', 'Moabit', 'Pankow', 'Tempelhof',
            'Steglitz', 'Lichtenberg', 'Weißensee', 'Spandau'
        ]

    def export_search_data(self, search_data: Dict[str, Any]) -> str:
        """Export search data as JSON for storage or debugging"""
        return json.dumps(search_data, indent=2, ensure_ascii=False)

    def import_search_data(self, json_data: str) -> Dict[str, Any]:
        """Import search data from JSON"""
        return json.loads(json_data)