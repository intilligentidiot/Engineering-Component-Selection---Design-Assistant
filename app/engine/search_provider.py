from abc import ABC, abstractmethod
from typing import List, Dict, Any

class SearchProvider(ABC):
    """
    Abstract Base Class for external product search providers.
    Isolates external search mechanisms (e.g., API, Web Search, Catalog Index)
    from the internal engineering calculation and discovery logic.
    """

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Execute an engineering search query and return raw candidate results.
        Must handle connectivity failures gracefully by returning an empty list or raising an exception.
        """
        pass


class SerpApiSearchProvider(SearchProvider):
    """
    Real Google Search provider using the official SerpApi Python client.
    Reads API key securely from SERPAPI_KEY environment variable.
    """
    def __init__(self, api_key: str = None):
        import os
        self.api_key = api_key or os.environ.get("SERPAPI_KEY")
        if not self.api_key:
            raise ValueError("INTERNET_SEARCH_NOT_CONFIGURED: SERPAPI_KEY environment variable is missing.")

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            import serpapi
            client = serpapi.Client(api_key=self.api_key)
            results_dict = client.search({
                "q": query,
                "engine": "google",
                "num": limit
            })

            organic_results = results_dict.get("organic_results", [])
            items = []

            for item in organic_results:
                title = item.get("title", "")
                # Prefer destination 'link' or 'redirect_link' returned by SerpApi
                raw_link = item.get("link") or item.get("redirect_link")
                snippet = item.get("snippet", "")
                source_domain = item.get("displayed_link", "") or item.get("source", "")

                # Check if link itself is a direct PDF datasheet
                is_pdf = raw_link and raw_link.lower().split("?")[0].endswith(".pdf")

                items.append({
                    # The display link is not a maker name; discover.clean_manufacturer() derives it from the URL
                    "manufacturer": None,
                    "snippet": snippet,
                    "product_name": title,
                    "model": None,
                    "part_number": None,
                    "product_url": raw_link if not is_pdf else None,
                    "datasheet_url": raw_link if is_pdf else None,
                    "image_url": item.get("thumbnail"),
                    "voltage_v": None,
                    "power_w": None,
                    "nominal_speed_rpm": None,
                    "nominal_torque_nm": None,
                    "gear_ratio": None,
                    "efficiency": None,
                    "max_output_torque_nm": None,
                    "availability_status": "AVAILABILITY_NOT_CONFIRMED",
                    "price": None,
                    "price_currency": "USD",
                    "cad_available": "False",
                    "cad_url": None,
                    "source": f"SerpApi ({source_domain or 'Google Search'})"
                })

            return items

        except Exception as e:
            print(f"SerpApi execution error: {e}")
            raise RuntimeError(f"INTERNET_SEARCH_ERROR: {str(e)}")

