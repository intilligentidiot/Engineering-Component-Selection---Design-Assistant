import re
import httpx
import io
import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

def _parse_value(text: str) -> Optional[float]:
    """Extracts a numeric float from a string like '24', '1/14', '81%'."""
    text = text.strip()
    if not text:
        return None
    # Handle ratios like 1/14 or 1:14
    m_ratio = re.match(r'^1\s*[/:]\s*(\d+(?:\.\d+)?)$', text)
    if m_ratio:
        return float(m_ratio.group(1))
    m_ratio2 = re.match(r'^(\d+(?:\.\d+)?)\s*[/:]\s*1$', text)
    if m_ratio2:
        return float(m_ratio2.group(1))
        
    # Handle percentage
    if text.endswith('%'):
        try:
            return float(text.replace('%','').strip()) / 100.0
        except ValueError:
            pass
            
    # Regular float
    # We might have units attached like '24 V', extract the first number
    m = re.search(r'(\d+(?:\.\d+)?)', text)
    if m:
        return float(m.group(1))
    return None


class ProductEnricher:
    """
    Stage 6.3: External Product Specification Enrichment.
    Deterministically fetches product pages/datasheets and extracts engineering
    specifications using strict context-based labels.
    Now includes DOM-aware HTML table parsing (Stage 6.3.1).
    """
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout, follow_redirects=True, verify=False)

    def __del__(self):
        try:
            self.client.close()
        except:
            pass

    def enrich(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched_candidates = []
        for candidate in candidates:
            enriched = dict(candidate)
            
            url_to_fetch = enriched.get("product_url") or enriched.get("datasheet_url")
            if not url_to_fetch:
                enriched_candidates.append(enriched)
                continue
                
            needs_enrichment = False
            for field in ["voltage_v", "nominal_speed_rpm", "nominal_torque_nm"]:
                if enriched.get(field) is None:
                    needs_enrichment = True
            
            if not needs_enrichment:
                enriched_candidates.append(enriched)
                continue

            try:
                response = self.client.get(url_to_fetch, headers={"User-Agent": "Mozilla/5.0 (EngineeringBot/1.0)"})
                response.raise_for_status()
                content = response.content
                
                text_content = ""
                content_type = response.headers.get("content-type", "").lower()
                
                if url_to_fetch.lower().split("?")[0].endswith(".pdf") or "application/pdf" in content_type:
                    if PdfReader:
                        try:
                            pdf = PdfReader(io.BytesIO(content))
                            text_content = " ".join([page.extract_text() or "" for page in pdf.pages])
                        except Exception:
                            text_content = ""
                else:
                    # Assume HTML
                    soup = BeautifulSoup(content, "html.parser")
                    # Try DOM-aware table extraction first
                    self._extract_from_tables(enriched, soup)
                    
                    text_content = soup.get_text(separator=' ', strip=True)
                
                if text_content:
                    # Regex fallback for anything still missing
                    self._extract_specifications(enriched, text_content)
                    
                # Mark provenance if anything was extracted during this fetch
                # Checking if we added any new non-none spec. Actually, we just say we ran extraction on this source.
                enriched["specification_source_url"] = url_to_fetch
                enriched["extracted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                enriched["specification_source"] = "Source Document Extraction"
                enriched["verification_status"] = "ENRICHED_FROM_SOURCE"
                    
            except Exception as e:
                pass
                
            enriched_candidates.append(enriched)
            
        return enriched_candidates

    def _extract_from_tables(self, candidate: Dict[str, Any], soup: BeautifulSoup):
        """
        DOM-aware extraction from <table> elements.
        Separates motor tables from gearbox tables to preserve context.
        """
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if not rows:
                continue
            
            # Analyze table structure
            # We'll extract all cell text in a 2D array
            grid = []
            for r in rows:
                cells = r.find_all(["th", "td"])
                grid.append([c.get_text(separator=' ', strip=True).lower() for c in cells])
                
            if not grid:
                continue

            # Determine table type: Motor or Gearbox
            is_gearbox = False
            is_motor = False
            
            # Flatten grid to search for keywords
            flat_grid = " ".join([" ".join(row) for row in grid])
            if "reduction ratio" in flat_grid or "gear ratio" in flat_grid:
                is_gearbox = True
            if "rated voltage" in flat_grid or "rated speed" in flat_grid:
                is_motor = True
                
            # If both, it might be a combined table or just a page with one large table. 
            # We'll process rows carefully.
            
            # Look for specific headers in columns (Header Row)
            header_row = grid[0]
            
            # We'll also support row-based headers (first column is header)
            col0 = [row[0] if len(row) > 0 else "" for row in grid]
            
            # Function to safely assign if unambiguous
            def assign_unambiguous(field, values, conversion=1.0):
                # Filter out None and deduplicate
                valid_vals = list(set([v for v in values if v is not None]))
                if len(valid_vals) == 1 and candidate.get(field) is None:
                    candidate[field] = valid_vals[0] * conversion

            # 1. Process column-based headers (e.g. Reduction Ratio | Rated Torque | Max Torque | Efficiency)
            ratio_idx = -1
            torque_idx = -1
            max_torque_idx = -1
            eff_idx = -1
            
            for i, h in enumerate(header_row):
                if "reduction ratio" in h or "gear ratio" in h: ratio_idx = i
                elif "rated torque" in h or "nominal torque" in h: torque_idx = i
                elif "max torque" in h or "max. torque" in h or "peak torque" in h: max_torque_idx = i
                elif "efficiency" in h: eff_idx = i
                
            if is_gearbox and ratio_idx != -1:
                # Column based gearbox table
                ratios = []
                torques = []
                max_torques = []
                effs = []
                
                # We need to detect torque units in headers or cells
                torque_unit_mult = 1.0
                if "mn.m" in header_row[torque_idx] or "mn·m" in header_row[torque_idx] or "mnm" in header_row[torque_idx]:
                    torque_unit_mult = 0.001
                
                for row in grid[1:]:
                    if len(row) <= max(ratio_idx, torque_idx, max_torque_idx, eff_idx):
                        continue
                    if ratio_idx != -1: ratios.append(_parse_value(row[ratio_idx]))
                    if torque_idx != -1:
                        # check cell for units if header didn't have it
                        t_str = row[torque_idx]
                        mult = torque_unit_mult
                        if "mn.m" in t_str or "mn·m" in t_str or "mnm" in t_str: mult = 0.001
                        v = _parse_value(t_str)
                        if v is not None: torques.append(v * mult)
                    if max_torque_idx != -1:
                        t_str = row[max_torque_idx]
                        mult = torque_unit_mult
                        if "mn.m" in t_str or "mn·m" in t_str or "mnm" in t_str: mult = 0.001
                        v = _parse_value(t_str)
                        if v is not None: max_torques.append(v * mult)
                    if eff_idx != -1: effs.append(_parse_value(row[eff_idx]))
                
                assign_unambiguous("gear_ratio", ratios)
                # Gearbox torque represents nominal output torque
                assign_unambiguous("nominal_torque_nm", torques)
                assign_unambiguous("max_output_torque_nm", max_torques)
                assign_unambiguous("efficiency", effs)

            # 2. Process row-based headers (e.g. Rated Voltage | 24 | 24)
            # Find target column if part number is present in header_row
            target_col = -1
            pn = (candidate.get("part_number") or "").lower()
            if pn:
                for i, h in enumerate(header_row):
                    if pn in h:
                        target_col = i
                        break

            for row in grid:
                if len(row) < 2: continue
                label = row[0]
                
                # Determine values to consider
                if target_col != -1 and target_col < len(row):
                    vals_to_parse = [row[target_col]]
                else:
                    # We might have a unit column in row[1]. 
                    # If row[1] is 'v', 'vdc', 'w', 'rpm', then values start from index 2
                    start_idx = 1
                    if row[1] in ["v", "vdc", "w", "rpm", "nm", "mn.m", "mnm", "mn·m", "a", "kw"]:
                        start_idx = 2
                    vals_to_parse = row[start_idx:]
                    
                parsed_vals = []
                unit_mult = 1.0
                
                # Check for unit in label or in the designated unit column
                unit_str = ""
                if len(row) > 1 and row[1] in ["v", "vdc", "w", "rpm", "nm", "mn.m", "mnm", "mn·m", "a", "kw"]:
                    unit_str = row[1]
                unit_str = unit_str or label
                
                if "mn.m" in unit_str or "mn·m" in unit_str or "mnm" in unit_str:
                    unit_mult = 0.001

                for vstr in vals_to_parse:
                    # also check inline units
                    local_mult = unit_mult
                    if "mn.m" in vstr or "mn·m" in vstr or "mnm" in vstr:
                        local_mult = 0.001
                    pv = _parse_value(vstr)
                    if pv is not None:
                        parsed_vals.append(pv * local_mult)
                
                if "rated voltage" in label or "nominal voltage" in label:
                    assign_unambiguous("voltage_v", parsed_vals)
                elif "rated speed" in label or "nominal speed" in label or "no-load speed" in label:
                    if not is_gearbox or is_motor: # It's motor speed
                        assign_unambiguous("nominal_speed_rpm", parsed_vals)
                elif "output power" in label or "rated power" in label or "motor power" in label:
                    assign_unambiguous("power_w", parsed_vals)
                elif "rated torque" in label or "nominal torque" in label or "continuous torque" in label:
                    # If it's a motor table, we can set nominal_torque_nm.
                    # Wait, if we are in a combined table or gear table, we set nominal_torque_nm.
                    # It's better to assign it to nominal_torque_nm.
                    assign_unambiguous("nominal_torque_nm", parsed_vals)


    def _extract_specifications(self, candidate: Dict[str, Any], text: str):
        """
        Applies strict regex matching based on labels to extract specifications.
        Fallback for plain text / unstructured text.
        """
        # Voltage
        if candidate.get("voltage_v") is None:
            m_v = re.search(r"(?:rated|nominal|operating|supply)\s+voltage[\s\:\-]+(\d+(?:\.\d+)?)\s*(?:V|volt|volts|vdc)", text, re.IGNORECASE)
            if m_v:
                candidate["voltage_v"] = float(m_v.group(1))
                
        # Speed
        if candidate.get("nominal_speed_rpm") is None:
            # Match "Output speed: 40 RPM", "Rated speed 3000 rev/min"
            # Explicitly require motor speed or output speed, not stall speed.
            m_rpm = re.search(r"(?:output|rated|nominal|no-load)\s+speed[\s\:\-]+(\d+(?:\.\d+)?)\s*(?:rpm|rev/min|r/min)", text, re.IGNORECASE)
            if m_rpm:
                candidate["nominal_speed_rpm"] = float(m_rpm.group(1))

        # Torque
        if candidate.get("nominal_torque_nm") is None:
            # Need to support mN.m as well
            m_tq = re.search(r"(?:continuous|rated|nominal|output)\s+(?:output\s+)?torque[\s\:\-]+(\d+(?:\.\d+)?)\s*(nm|n-m|n\xb7m|n\u00b7m|mn\.m|mnm|mn\xb7m)", text, re.IGNORECASE)
            if m_tq:
                val = float(m_tq.group(1))
                unit = m_tq.group(2).lower()
                if "mn" in unit:
                    val *= 0.001
                candidate["nominal_torque_nm"] = val

        # Power
        if candidate.get("power_w") is None:
            m_p = re.search(r"(?:rated|nominal|motor|output)\s+power[\s\:\-]+(\d+(?:\.\d+)?)\s*(W|kW)", text, re.IGNORECASE)
            if m_p:
                val = float(m_p.group(1))
                if m_p.group(2).lower() == "kw":
                    val *= 1000
                candidate["power_w"] = val

        # Gear Ratio
        if candidate.get("gear_ratio") is None:
            m_gr = re.search(r"(?:gear|reduction)\s+ratio[\s\:\-]+(\d+(?:\.\d+)?)\s*[:/]\s*1", text, re.IGNORECASE)
            if m_gr:
                candidate["gear_ratio"] = float(m_gr.group(1))

        # Efficiency
        if candidate.get("efficiency") is None:
            m_eff = re.search(r"(?:gearbox\s+)?efficiency[\s\:\-]+(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
            if m_eff:
                candidate["efficiency"] = float(m_eff.group(1)) / 100.0
