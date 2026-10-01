import os
import json
import httpx
from typing import Optional
from app.ai.requirement_parser import RequirementParser, ParseResult, ParsedRequirements

class RealRequirementParser(RequirementParser):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def parse(self, text: str) -> ParseResult:
        if not self.api_key:
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["OPENAI_API_KEY is missing. AI parsing is unavailable."],
                parser_status="ERROR_CONFIGURATION_MISSING"
            )

        prompt = f"""
You are an engineering assistant. Extract mechanical requirements from the user's text.
Output MUST be raw JSON. Do not use markdown blocks.
Use the following keys exactly:
- "requirements": an object containing:
    - "required_torque_nm": float or null. Convert to Nm if obvious, else null.
    - "required_speed_rpm": float or null. Convert to RPM if obvious, else null.
    - "max_voltage_v": float or null. Convert to Volts if obvious, else null.
    - "service_factor": float or null.
    - "application": string or null.
- "clarifications": an array of strings. Add a string here if an unsupported/ambiguous unit is provided or if clarification is needed.

Rules:
1. Only output valid JSON matching this exact structure.
2. If a value is not provided, use null. Do not invent defaults.
3. If an unsupported unit is provided (e.g. lb-in, oz-in), leave the field null and add a clarification.

Text: "{text}"
"""

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-3.5-turbo",
                        "messages": [{"role": "system", "content": prompt}],
                        "temperature": 0.0,
                        "response_format": {"type": "json_object"}
                    }
                )
            
            if response.status_code != 200:
                return ParseResult(
                    requirements=ParsedRequirements(),
                    missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                    clarifications=[f"AI Provider Error: HTTP {response.status_code}"],
                    parser_status="ERROR_PROVIDER_FAILED"
                )

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            req_data = parsed.get("requirements", {})
            reqs = ParsedRequirements(
                required_torque_nm=req_data.get("required_torque_nm"),
                required_speed_rpm=req_data.get("required_speed_rpm"),
                max_voltage_v=req_data.get("max_voltage_v"),
                service_factor=req_data.get("service_factor"),
                application=req_data.get("application")
            )

            clarifications = parsed.get("clarifications", [])

            missing = []
            if reqs.required_torque_nm is None: missing.append("required_torque_nm")
            if reqs.required_speed_rpm is None: missing.append("required_speed_rpm")
            if reqs.max_voltage_v is None: missing.append("max_voltage_v")

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

        except httpx.TimeoutException:
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["AI Provider Timeout."],
                parser_status="ERROR_PROVIDER_TIMEOUT"
            )
        except json.JSONDecodeError:
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["AI Provider returned malformed JSON."],
                parser_status="ERROR_MALFORMED_RESPONSE"
            )
        except Exception as e:
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=[f"Unexpected error: {str(e)}"],
                parser_status="ERROR_UNEXPECTED"
            )
