import pytest
from bs4 import BeautifulSoup
from scratch.product_enrichment_updated import ProductEnricher

def test_1_output_power():
    e = ProductEnricher()
    c = {}
    soup = BeautifulSoup("<table><tr><td>Output Power</td><td>W</td><td>12.6</td></tr></table>", "html.parser")
    e._extract_from_tables(c, soup)
    assert c["power_w"] == 12.6

def test_2_rated_speed():
    e = ProductEnricher()
    c = {}
    soup = BeautifulSoup("<table><tr><td>Rated Speed</td><td>RPM</td><td>3000</td></tr></table>", "html.parser")
    e._extract_from_tables(c, soup)
    assert c["nominal_speed_rpm"] == 3000.0

def test_3_rated_torque():
    e = ProductEnricher()
    c = {}
    soup = BeautifulSoup("<table><tr><td>Rated Torque</td><td>mN.m</td><td>40</td></tr></table>", "html.parser")
    e._extract_from_tables(c, soup)
    assert c["nominal_torque_nm"] == 0.040

def test_4_gearbox_table():
    e = ProductEnricher()
    c = {}
    html = '''<table>
    <tr><th>Reduction Ratio</th><th>Rated Torque</th><th>Max Torque</th><th>Efficiency</th></tr>
    <tr><td>1/14</td><td>2</td><td>6</td><td>81%</td></tr>
    </table>'''
    soup = BeautifulSoup(html, "html.parser")
    e._extract_from_tables(c, soup)
    assert c["gear_ratio"] == 14.0
    assert c["nominal_torque_nm"] == 2.0
    assert c["max_output_torque_nm"] == 6.0
    assert c["efficiency"] == 0.81

def test_5_motor_speed_not_output_speed():
    e = ProductEnricher()
    c = {}
    # The requirement is that a motor rated speed is motor speed, not gearbox output speed.
    # We assign nominal_speed_rpm for both, because the deterministic engine divides nominal_speed_rpm by gear_ratio!
    # "Motor 3000 RPM must NOT become gearbox output RPM."
    # The existing schema maps 'nominal_speed_rpm' to the motor's speed when evaluating.
    # Let's ensure the label 'Rated Speed' assigns it to 'nominal_speed_rpm' correctly.
    soup = BeautifulSoup("<table><tr><td>Rated Speed</td><td>RPM</td><td>3000</td></tr></table>", "html.parser")
    e._extract_from_tables(c, soup)
    assert c["nominal_speed_rpm"] == 3000.0
    assert "output_speed_rpm" not in c # We don't magically make it output speed

def test_6_mNm_conversion():
    e = ProductEnricher()
    c = {}
    html = '''<table>
    <tr><th>Reduction Ratio</th><th>Rated Torque (mN.m)</th></tr>
    <tr><td>14</td><td>20</td></tr>
    </table>'''
    soup = BeautifulSoup(html, "html.parser")
    e._extract_from_tables(c, soup)
    assert c["nominal_torque_nm"] == 0.020
    
def test_7_multiple_ratios_not_collapsed():
    e = ProductEnricher()
    c = {}
    html = '''<table>
    <tr><th>Reduction Ratio</th><th>Rated Torque</th></tr>
    <tr><td>14</td><td>2</td></tr>
    <tr><td>20</td><td>3</td></tr>
    </table>'''
    soup = BeautifulSoup(html, "html.parser")
    e._extract_from_tables(c, soup)
    assert c.get("gear_ratio") is None # Unambiguous constraint prevents picking one
    assert c.get("nominal_torque_nm") is None

def test_8_regex_fallback():
    e = ProductEnricher()
    c = {}
    e._extract_specifications(c, "Continuous output torque: 1.15 Nm")
    assert c["nominal_torque_nm"] == 1.15

def test_9_mNm_regex():
    e = ProductEnricher()
    c = {}
    e._extract_specifications(c, "Continuous output torque: 20 mN.m")
    assert c["nominal_torque_nm"] == 0.02

