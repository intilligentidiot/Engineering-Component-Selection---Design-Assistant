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
        
    # Check if this is a list of multiple ratios (e.g. "1/14 1/19 1/22")
    # If it contains multiple ratios, we return None (unambiguous rule)
    if text.count('/') > 1 or text.count(':') > 1:
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
                    soup = BeautifulSoup(content, "html.parser")
                    self._extract_from_tables(enriched, soup)
                    text_content = soup.get_text(separator=' ', strip=True)
                
                if text_content:
                    self._extract_specifications(enriched, text_content)
                    
                enriched["specification_source_url"] = url_to_fetch
                enriched["extracted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                enriched["specification_source"] = "Source Document Extraction"
                enriched["verification_status"] = "ENRICHED_FROM_SOURCE"
                    
            except Exception as e:
                pass
                
            enriched_candidates.append(enriched)
            
        return enriched_candidates

    def _extract_from_tables(self, candidate: Dict[str, Any], soup: BeautifulSoup):
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if not rows:
                continue
            
            grid = []
            for r in rows:
                cells = r.find_all(["th", "td"])
                grid.append([c.get_text(separator=' ', strip=True).lower() for c in cells])
                
            if not grid:
                continue

            is_gearbox = False
            is_motor = False
            flat_grid = " ".join([" ".join(row) for row in grid])
            if "reduction ratio" in flat_grid or "gear ratio" in flat_grid:
                is_gearbox = True
            if "rated voltage" in flat_grid or "rated speed" in flat_grid:
                is_motor = True
                
            # Find the true header row for column-based data (Gearbox usually)
            col_header_row = grid[0]
            for row in grid:
                if any("reduction ratio" in c or "gear ratio" in c for c in row):
                    col_header_row = row
                    break

            def assign_unambiguous(field, values, conversion=1.0):
                valid_vals = list(set([v for v in values if v is not None]))
                if len(valid_vals) == 1 and candidate.get(field) is None:
                    candidate[field] = valid_vals[0] * conversion

            # 1. Process column-based headers (Gearbox)
            ratio_idx = -1
            torque_idx = -1
            max_torque_idx = -1
            eff_idx = -1
            
            for i, h in enumerate(col_header_row):
                if "reduction ratio" in h or "gear ratio" in h: ratio_idx = i
                elif "rated torque" in h or "nominal torque" in h: torque_idx = i
                elif "max torque" in h or "max. torque" in h or "peak torque" in h: max_torque_idx = i
                elif "efficiency" in h: eff_idx = i
                
            if is_gearbox and ratio_idx != -1:
                ratios, torques, max_torques, effs = [], [], [], []
                
                torque_unit_mult = 1.0
                if "mn.m" in col_header_row[torque_idx] or "mn·m" in col_header_row[torque_idx] or "mnm" in col_header_row[torque_idx]:
                    torque_unit_mult = 0.001
                
                # Iterate rows below the col_header_row
                header_index = grid.index(col_header_row)
                for row in grid[header_index+1:]:
                    if len(row) <= max(ratio_idx, torque_idx, max_torque_idx, eff_idx):
                        continue
                    if ratio_idx != -1: ratios.append(_parse_value(row[ratio_idx]))
                    if torque_idx != -1:
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
                assign_unambiguous("nominal_torque_nm", torques)
                assign_unambiguous("max_output_torque_nm", max_torques)
                assign_unambiguous("efficiency", effs)

            # Find the true header row for row-based data (Motor models)
            model_header_row = grid[0]
            for row in grid:
                if any("model" in c or "part number" in c for c in row):
                    model_header_row = row
                    break

            target_col = -1
            pn = (candidate.get("part_number") or "").lower()
            if pn:
                for i, h in enumerate(model_header_row):
                    if pn in h:
                        target_col = i
                        break

            # 2. Process row-based headers
            for row in grid:
                if len(row) < 2: continue
                label = row[0]
                
                if target_col != -1 and target_col < len(row):
                    vals_to_parse = [row[target_col]]
                else:
                    start_idx = 1
                    if len(row) > 1 and row[1] in ["v", "vdc", "w", "rpm", "nm", "n.m", "mn.m", "mnm", "mn·m", "a", "kw"]:
                        start_idx = 2
                    vals_to_parse = row[start_idx:]
                    
                parsed_vals = []
                unit_mult = 1.0
                
                unit_str = ""
                if len(row) > 1 and row[1] in ["v", "vdc", "w", "rpm", "nm", "n.m", "mn.m", "mnm", "mn·m", "a", "kw"]:
                    unit_str = row[1]
                unit_str = unit_str or label
                
                if "mn.m" in unit_str or "mn·m" in unit_str or "mnm" in unit_str:
                    unit_mult = 0.001

                for vstr in vals_to_parse:
                    local_mult = unit_mult
                    if "mn.m" in vstr or "mn·m" in vstr or "mnm" in vstr:
                        local_mult = 0.001
                    pv = _parse_value(vstr)
                    if pv is not None:
                        parsed_vals.append(pv * local_mult)
                
                if "rated voltage" in label or "nominal voltage" in label:
                    assign_unambiguous("voltage_v", parsed_vals)
                elif "rated speed" in label or "nominal speed" in label or "no-load speed" in label:
                    if not is_gearbox or is_motor:
                        assign_unambiguous("nominal_speed_rpm", parsed_vals)
                elif "output power" in label or "rated power" in label or "motor power" in label:
                    assign_unambiguous("power_w", parsed_vals)
                elif "rated torque" in label or "nominal torque" in label or "continuous torque" in label:
                    assign_unambiguous("nominal_torque_nm", parsed_vals)


    def _extract_specifications(self, candidate: Dict[str, Any], text: str):
        if candidate.get("voltage_v") is None:
            m_v = re.search(r"(?:rated|nominal|operating|supply)\s+voltage[\s\:\-]+(\d+(?:\.\d+)?)\s*(?:V|volt|volts|vdc)", text, re.IGNORECASE)
            if m_v:
                candidate["voltage_v"] = float(m_v.group(1))
                
        if candidate.get("nominal_speed_rpm") is None:
            m_rpm = re.search(r"(?:output|rated|nominal|no-load)\s+speed[\s\:\-]+(\d+(?:\.\d+)?)\s*(?:rpm|rev/min|r/min)", text, re.IGNORECASE)
            if m_rpm:
                candidate["nominal_speed_rpm"] = float(m_rpm.group(1))

        if candidate.get("nominal_torque_nm") is None:
            m_tq = re.search(r"(?:continuous|rated|nominal|output)\s+(?:output\s+)?torque[\s\:\-]+(\d+(?:\.\d+)?)\s*(nm|n-m|n\xb7m|n\u00b7m|mn\.m|mnm|mn\xb7m)", text, re.IGNORECASE)
            if m_tq:
                val = float(m_tq.group(1))
                unit = m_tq.group(2).lower()
                if "mn" in unit:
                    val *= 0.001
                candidate["nominal_torque_nm"] = val

        if candidate.get("power_w") is None:
            m_p = re.search(r"(?:rated|nominal|motor|output)\s+power[\s\:\-]+(\d+(?:\.\d+)?)\s*(W|kW)", text, re.IGNORECASE)
            if m_p:
                val = float(m_p.group(1))
                if m_p.group(2).lower() == "kw":
                    val *= 1000
                candidate["power_w"] = val

        if candidate.get("gear_ratio") is None:
            m_gr = re.search(r"(?:gear|reduction)\s+ratio[\s\:\-]+(\d+(?:\.\d+)?)\s*[:/]\s*1", text, re.IGNORECASE)
            if m_gr:
                candidate["gear_ratio"] = float(m_gr.group(1))

        if candidate.get("efficiency") is None:
            m_eff = re.search(r"(?:gearbox\s+)?efficiency[\s\:\-]+(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE)
            if m_eff:
                candidate["efficiency"] = float(m_eff.group(1)) / 100.0
