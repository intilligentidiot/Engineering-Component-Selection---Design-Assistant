from abc import ABC, abstractmethod
from typing import Optional, List
from pydantic import BaseModel
import re

class ParsedRequirements(BaseModel):
    required_torque_nm: Optional[float] = None
    required_speed_rpm: Optional[float] = None
    max_voltage_v: Optional[float] = None
    service_factor: Optional[float] = None
    application: Optional[str] = None

class ParseResult(BaseModel):
    requirements: ParsedRequirements
    missing_fields: List[str]
    clarifications: List[str]
    parser_status: str

class RequirementParser(ABC):
    """
    Abstract interface for AI requirement parsing.
    Decouples the engineering layer from specific LLM providers.
    """
    @abstractmethod
    def parse(self, text: str) -> ParseResult:
        pass

class MockRequirementParser(RequirementParser):
    """
    Deterministic mock parser for Stage 7.1.
    Uses regex to extract explicit engineering values.
    """
    def parse(self, text: str) -> ParseResult:
        reqs = ParsedRequirements()
        clarifications = []
        
        # 1. Look for ambiguous/unsupported units (lb-in, lb-ft, kg-cm)
        unsupported_match = re.search(r'([\d\.]+)\s*(lb-in|lb-ft|kg-cm|oz-in)', text, re.IGNORECASE)
        if unsupported_match:
            clarifications.append(f"Unsupported unit '{unsupported_match.group(2)}' detected. Please provide torque in Nm.")
        
        # Torque
        torque_match = re.search(r'(\d+(?:\.\d+)?)\s*(nm|n-m|n·m)\b', text, re.IGNORECASE)
        if torque_match:
            reqs.required_torque_nm = float(torque_match.group(1))

        # Speed
        speed_match = re.search(r'(\d+(?:\.\d+)?)\s*(rpm|rev/min|r/min)\b', text, re.IGNORECASE)
        if speed_match:
            reqs.required_speed_rpm = float(speed_match.group(1))

        # Voltage
        voltage_match = re.search(r'(\d+(?:\.\d+)?)\s*(v|volt|volts)\b', text, re.IGNORECASE)
        if voltage_match:
            reqs.max_voltage_v = float(voltage_match.group(1))

        # Service Factor
        sf_match = re.search(r'(?:service factor(?: of)?|sf)[\s:]*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
        if sf_match:
            reqs.service_factor = float(sf_match.group(1))

        # Application
        app_match = re.search(r'for a ([a-zA-Z\s]+)(?:[\.,]|$)', text, re.IGNORECASE)
        if app_match:
            reqs.application = app_match.group(1).strip()

        # Determine missing fields (for basic engineering calculation)
        missing = []
        if reqs.required_torque_nm is None:
            missing.append("required_torque_nm")
        if reqs.required_speed_rpm is None:
            missing.append("required_speed_rpm")
        if reqs.max_voltage_v is None:
            missing.append("max_voltage_v")

        if clarifications:
            status = "NEEDS_CLARIFICATION"
        elif missing:
            status = "PARTIAL"
            clarifications.append("Please provide the missing engineering specifications to get a recommendation.")
        else:
            status = "PARSED"

        return ParseResult(
            requirements=reqs,
            missing_fields=missing,
            clarifications=clarifications,
            parser_status=status
        )
