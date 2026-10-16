const fs = require("fs");
global.window = {}; global.document = { addEventListener() {}, querySelectorAll: () => [] };
global.localStorage = { getItem: () => null, setItem() {} };
eval(fs.readFileSync(process.argv[2], "utf8"));
const U = window.Units, c = U.convert;
const checks = [
  ["7772 N -> kN", c(7772, "N", "kN"), 7.772],
  ["7772 N -> lbf", c(7772, "N", "lbf"), 1747.24],
  ["2685 N·m -> lbf·ft", c(2685, "N·m", "lbf·ft"), 1980.36],
  ["2685 Nm (alias) -> kN·m", c(2685, "Nm", "kN·m"), 2.685],
  ["21.31 kW -> hp", c(21.31, "kW", "hp"), 28.577],
  ["140 MPa -> psi", c(140, "MPa", "psi"), 20305.3],
  ["140 MPa -> N/mm²", c(140, "MPa", "N/mm²"), 140],
  ["630 mm -> in", c(630, "mm", "in"), 24.803],
  ["2.5 m/s -> ft/min", c(2.5, "m/s", "ft/min"), 492.126],
  ["1000 t/h -> short ton/h", c(1000, "t/h", "short ton/h"), 1102.31],
  ["25 kg/m -> lb/ft", c(25, "kg/m", "lb/ft"), 16.799],
  ["75.79 rpm -> rad/s", c(75.79, "rpm", "rad/s"), 7.9367],
  ["180 deg -> rad", c(180, "deg", "rad"), Math.PI],
  ["100 °C -> °F", c(100, "°C", "°F"), 212],
  ["0 °C -> K", c(0, "°C", "K"), 273.15],
  ["1 kWh -> J", c(1, "kWh", "J"), 3.6e6],
  ["N -> rpm (different family: unchanged)", c(5, "N", "rpm"), 5],
];
let bad = 0;
// Every unit offered in a dropdown must have a full name
for (const [fam, units] of Object.entries(U.FAMILIES)) {
  for (const u of Object.keys(units)) {
    if (!U.fullName(u)) { bad++; console.log("BAD missing full name:", fam, u); }
  }
}
// Factor text shown under the working
const ft = U.factorText("N·m", "lbf·ft");
if (ft !== "1 N·m = 0.7376 lbf·ft") { bad++; console.log("BAD factor text:", ft); } else console.log("OK  factor text", ft);
const tt = U.factorText("°C", "°F");
if (tt !== "°C → °F") { bad++; console.log("BAD temperature factor text:", tt); } else console.log("OK  temperature factor text", tt);
for (const [name, got, want] of checks) {
  const ok = Math.abs(got - want) <= Math.abs(want) * 2e-4 + 1e-9;
  if (!ok) bad++;
  console.log(ok ? "OK " : "BAD", name, got);
}
console.log(bad ? `${bad} FAILED` : "ALL OK");
