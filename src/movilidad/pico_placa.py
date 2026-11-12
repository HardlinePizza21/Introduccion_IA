"""Reglas de pico y placa de Medellín, segundo semestre de 2026.

Fuente: Alcaldía de Medellín, "La nueva rotación del Pico y Placa en Medellín comenzará
a regir a partir del lunes 3 de agosto" (corpus/pico_y_placa_2026_2.md). Vigencia:
3-ago-2026 a 29-ene-2027, lunes a viernes de 5:00 a. m. a 8:00 p. m.
"""
from __future__ import annotations

import datetime as dt

SOURCE = "pico_y_placa_2026_2.md (Alcaldía de Medellín)"
VALID_FROM = dt.date(2026, 8, 3)
VALID_TO = dt.date(2027, 1, 29)
START_HOUR, END_HOUR = 5, 20  # 5:00 a 20:00
ROTATION = {0: (5, 8), 1: (1, 4), 2: (0, 2), 3: (3, 6), 4: (7, 9)}  # weekday() -> dígitos
DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
EXEMPT_VEHICLES = ("eléctrico", "híbrido", "gas natural vehicular")


def check(plate: str, date: str | dt.date, hour: int | None = None, vehicle: str = "carro",
          fuel: str = "gasolina") -> dict:
    """Indica si un vehículo tiene restricción. Carros: último dígito; motos: primer dígito."""
    if isinstance(date, str):
        try:
            date = dt.date.fromisoformat(date.strip())
        except ValueError as exc:
            raise ValueError("La fecha debe tener formato AAAA-MM-DD.") from exc
    digits = [c for c in str(plate) if c.isdigit()]
    if not digits:
        raise ValueError("La placa debe contener al menos un dígito.")
    is_moto = vehicle.lower().startswith("moto")
    digit = int(digits[0] if is_moto else digits[-1])
    out = {"placa": plate, "digito_evaluado": digit, "fecha": date.isoformat(), "dia": DAY_NAMES[date.weekday()],
           "fuente": SOURCE, "restringido": False}
    if not VALID_FROM <= date <= VALID_TO:
        out["nota"] = "Fecha fuera de la vigencia de la rotación cargada (3-ago-2026 a 29-ene-2027); consulte la norma vigente."
        out["restringido"] = None
        return out
    if any(x in fuel.lower() for x in ("eléctr", "electr", "híbr", "hibr", "gas natural", "gnv")):
        out["nota"] = "Vehículos eléctricos, híbridos y a gas natural vehicular están exentos."
        return out
    restricted_digits = ROTATION.get(date.weekday())
    out["digitos_restringidos_dia"] = list(restricted_digits) if restricted_digits else []
    if restricted_digits is None:
        out["nota"] = "Sábados, domingos (y festivos) no aplica pico y placa."
        return out
    if digit in restricted_digits:
        if hour is not None and not START_HOUR <= int(hour) < END_HOUR:
            out["nota"] = f"El dígito {digit} tiene restricción ese día, pero solo entre 5:00 y 20:00."
        else:
            out["restringido"] = True
            out["nota"] = (f"Restricción de 5:00 a 20:00 para dígito {digit} el {DAY_NAMES[date.weekday()]}. "
                           "No aplica en vías exentas (Av. Regional, Autopista Sur en Medellín, Las Palmas). "
                           "No se verifican festivos.")
    else:
        out["nota"] = f"El dígito {digit} no tiene restricción el {DAY_NAMES[date.weekday()]}."
    return out
