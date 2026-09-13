"""
Calculadora de Tarifas Eléctricas para Autoconsumo Solar
=========================================================
Emilio Vimelli · San Fernando, Cádiz · Instalación FV con excedentes
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


# ─── CONSTANTES DEL USUARIO ──────────────────────────────────────────────────

KWH_ANUAL     = 2122    # kWh comprados a la red (año 2025 real)
EXCEDENTES    = 3776    # kWh inyectados a la red (año 2025 real)
DIAS          = 365
P1_KW         = 3.45   # kW potencia contratada P1
P2_KW         = 3.45   # kW potencia contratada P2
BONO_SOCIAL   = 0.019121   # €/día
ALQUILER      = 0.026630   # €/día
OTROS         = (BONO_SOCIAL + ALQUILER) * DIAS  # ~16.70 €/año
IMP_ELEC      = 0.05112696  # 5,11%
IVA           = 0.21        # 21%
BAT_VIRTUAL   = 79          # € valor real anual batería virtual Naturgy

# Distribución horaria real (del CSV e-distribución ene-mar 2026)
PCT_PUNTA = 0.255   # 25,5% — horas 10-14h y 18-22h laborables
PCT_LLANO = 0.375   # 37,5% — horas 8-10h, 14-18h, 22-24h laborables
PCT_VALLE = 0.370   # 37,0% — 0-8h laborables + todo fin de semana


# ─── DATACLASS OFERTA ────────────────────────────────────────────────────────

@dataclass
class Oferta:
    nombre: str

    # Energía
    dh: bool = False                    # ¿Tiene discriminación horaria?
    kwh_unico: Optional[float] = None   # Precio único €/kWh
    kwh_punta: Optional[float] = None   # Precio punta €/kWh (si dh=True)
    kwh_llano: Optional[float] = None   # Precio llano €/kWh (si dh=True)
    kwh_valle: Optional[float] = None   # Precio valle €/kWh (si dh=True)

    # Potencia
    pot_unica: bool = True              # ¿Precio único para P1 y P2?
    pot_unico: Optional[float] = None  # €/kW·día (si pot_unica=True)
    pot_p1: Optional[float] = None     # €/kW·día P1 (si pot_unica=False)
    pot_p2: Optional[float] = None     # €/kW·día P2 (si pot_unica=False)

    # Excedente y batería
    excedente: float = 0.07
    bateria_virtual: bool = False

    # Tarifa plana (caso especial)
    tarifa_plana: bool = False
    coste_fijo_anual: Optional[float] = None

    notas: str = ""


# ─── CÁLCULO ─────────────────────────────────────────────────────────────────

def calcular(oferta: Oferta) -> dict:
    """
    Devuelve un dict con el desglose completo y el coste real anual.
    El coste real = factura anual − valor batería virtual (si la tiene).
    """

    if oferta.tarifa_plana:
        return {
            "energia":    oferta.coste_fijo_anual,
            "excedentes": 0,
            "potencia":   0,
            "otros":      0,
            "subtotal":   oferta.coste_fijo_anual,
            "imp_elec":   0,
            "iva":        0,
            "factura":    oferta.coste_fijo_anual,
            "bat_virtual": 0,
            "coste_real": oferta.coste_fijo_anual,
        }

    # Energía
    if oferta.dh:
        energia = (
            KWH_ANUAL * PCT_PUNTA * oferta.kwh_punta +
            KWH_ANUAL * PCT_LLANO * oferta.kwh_llano +
            KWH_ANUAL * PCT_VALLE * oferta.kwh_valle
        )
    else:
        energia = KWH_ANUAL * oferta.kwh_unico

    # Excedentes
    exc = EXCEDENTES * oferta.excedente

    # Potencia
    if oferta.pot_unica:
        pot = (P1_KW + P2_KW) * DIAS * oferta.pot_unico
    else:
        pot = P1_KW * DIAS * oferta.pot_p1 + P2_KW * DIAS * oferta.pot_p2

    # Impuestos
    subtotal = energia - exc + pot + OTROS
    imp      = subtotal * IMP_ELEC
    iva      = (subtotal + imp) * IVA
    factura  = subtotal + imp + iva

    # Batería virtual
    bat = BAT_VIRTUAL if oferta.bateria_virtual else 0
    coste_real = factura - bat

    return {
        "energia":    round(energia, 2),
        "excedentes": round(exc, 2),
        "potencia":   round(pot, 2),
        "otros":      round(OTROS, 2),
        "subtotal":   round(subtotal, 2),
        "imp_elec":   round(imp, 2),
        "iva":        round(iva, 2),
        "factura":    round(factura, 2),
        "bat_virtual": bat,
        "coste_real": round(coste_real, 2),
    }


# ─── ALERTAS ─────────────────────────────────────────────────────────────────

def alertas(oferta: Oferta, d: dict) -> list:
    msgs = []
    if not oferta.tarifa_plana:
        if d["potencia"] > 250:
            msgs.append(f"⚠  POTENCIA MUY ALTA: {d['potencia']:.0f} €/año (ref. regulada: 181 €)")
        if oferta.excedente < 0.07:
            perdida = round(EXCEDENTES * (0.07 - oferta.excedente), 0)
            msgs.append(f"⚠  Excedente bajo ({oferta.excedente} €/kWh): pierdes {perdida:.0f} €/año vs 0,07")
        if not oferta.bateria_virtual:
            msgs.append("ℹ  Sin batería virtual: en invierno no tienes colchón del verano (−79 €/año)")
    return msgs


# ─── RANKING ─────────────────────────────────────────────────────────────────

def ranking(ofertas: list[Oferta]) -> list[tuple[Oferta, dict]]:
    resultados = [(o, calcular(o)) for o in ofertas]
    return sorted(resultados, key=lambda x: x[1]["coste_real"])


def imprimir_ranking(ofertas: list[Oferta], verbose: bool = False):
    ranked = ranking(ofertas)
    mejor = ranked[0][1]["coste_real"]

    print("\n" + "═" * 70)
    print("  RANKING DE TARIFAS — coste real anual con tus datos")
    print("  (consumo: 2.122 kWh · excedentes: 3.776 kWh · pot: 3,45+3,45 kW)")
    print("═" * 70)

    for i, (oferta, d) in enumerate(ranked):
        diff   = d["coste_real"] - mejor
        medalla = "⭐" if i == 0 else f"{i+1}."
        bat_tag = " +bat.virtual" if oferta.bateria_virtual else ""
        sep = "  ←─── MÁS DE 100€ POR ENCIMA ───" if diff > 100 and (i == 0 or ranked[i-1][1]["coste_real"] - mejor <= 100) else ""

        if sep:
            print(f"\n{'─'*70}")
            print(f"  {sep}")
            print(f"{'─'*70}")

        diff_str = f"(+{diff:.0f} €/año)" if diff > 0 else ""
        print(f"\n  {medalla:3} {oferta.nombre}{bat_tag}")
        print(f"       Coste real: {d['coste_real']:>6.0f} €/año  ·  {d['coste_real']/12:>5.2f} €/mes  {diff_str}")

        if verbose:
            print(f"       Factura bruta: {d['factura']:.2f} €  |  "
                  f"Energía: {d['energia']:.2f}  |  "
                  f"Exc: −{d['excedentes']:.2f}  |  "
                  f"Pot: {d['potencia']:.2f}")
            for alerta in alertas(oferta, d):
                print(f"       {alerta}")

        if oferta.notas:
            print(f"       → {oferta.notas}")

    print("\n" + "═" * 70)
    print(f"  Mejor opción: {ranked[0][0].nombre}")
    print(f"  Ahorro vs tu tarifa actual (Naturgy 2026): "
          f"{next(d['coste_real'] for o,d in ranked if 'actual' in o.nombre.lower()) - mejor:.0f} €/año")
    print("═" * 70 + "\n")


# ─── CARGAR DESDE JSON ────────────────────────────────────────────────────────

def desde_json(ruta: str) -> list[Oferta]:
    """Carga ofertas desde el JSON generado en el análisis."""
    data = json.loads(Path(ruta).read_text(encoding="utf-8"))
    ofertas = []
    for o in data["ofertas"]:
        ofertas.append(Oferta(
            nombre          = o["nombre"],
            dh              = o.get("dh", False),
            kwh_unico       = o.get("kwh_unico"),
            kwh_punta       = o.get("kwh_punta"),
            kwh_llano       = o.get("kwh_llano"),
            kwh_valle       = o.get("kwh_valle"),
            pot_unica       = o.get("pot_unica", True),
            pot_unico       = o.get("pot_unico"),
            pot_p1          = o.get("pot_p1"),
            pot_p2          = o.get("pot_p2"),
            excedente       = o.get("excedente") or 0.0,
            bateria_virtual = o.get("bateria_virtual", False),
            tarifa_plana    = o.get("tarifa_plana", False),
            coste_fijo_anual= o.get("coste_fijo_mes", 0) * 12 if o.get("tarifa_plana") else None,
            notas           = o.get("notas", ""),
        ))
    return ofertas


# ─── NUEVA OFERTA INTERACTIVA ─────────────────────────────────────────────────

def nueva_oferta_interactiva() -> Oferta:
    """Pide los 4 datos por consola y devuelve una Oferta."""
    print("\n─── INTRODUCE NUEVA OFERTA ───")
    nombre = input("Nombre comercializadora: ").strip() or "Nueva oferta"

    dh = input("¿Tiene discriminación horaria? (s/n): ").lower() == "s"
    if dh:
        kwh_punta = float(input("  Precio punta (€/kWh): "))
        kwh_llano = float(input("  Precio llano (€/kWh): "))
        kwh_valle = float(input("  Precio valle (€/kWh): "))
        kwh_unico = kwh_punta = kwh_llano = kwh_valle
    else:
        kwh_unico = float(input("Precio kWh único (€/kWh): "))
        kwh_punta = kwh_llano = kwh_valle = None

    pot_dos = input("¿Tiene precio distinto P1 y P2? (s/n): ").lower() == "s"
    if pot_dos:
        pot_p1    = float(input("  Potencia P1 (€/kW·día): "))
        pot_p2    = float(input("  Potencia P2 (€/kW·día): "))
        pot_unico = None
        pot_unica = False
    else:
        raw = input("Término de potencia único (€/kW·día o €/kW·mes si acabas en /mes): ")
        if "/mes" in raw.lower():
            pot_unico = float(raw.replace("/mes","").strip()) / 30.4375
            print(f"  → Convertido a €/kW·día: {pot_unico:.5f}")
        else:
            pot_unico = float(raw)
        pot_p1 = pot_p2 = None
        pot_unica = True

    excedente = float(input("Precio excedente (€/kWh): "))
    bat       = input("¿Incluye batería virtual? (s/n): ").lower() == "s"

    return Oferta(
        nombre          = nombre,
        dh              = dh,
        kwh_unico       = kwh_unico if not dh else None,
        kwh_punta       = kwh_punta if dh else None,
        kwh_llano       = kwh_llano if dh else None,
        kwh_valle       = kwh_valle if dh else None,
        pot_unica       = pot_unica,
        pot_unico       = pot_unico,
        pot_p1          = pot_p1,
        pot_p2          = pot_p2,
        excedente       = excedente,
        bateria_virtual = bat,
    )


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Cargar ofertas desde JSON si existe, si no usar las hardcodeadas
    json_path = Path("tarifas_solar.json")
    if json_path.exists():
        print(f"✓ Cargando ofertas desde {json_path}")
        ofertas = desde_json(str(json_path))
    else:
        print("ℹ  JSON no encontrado — usando ofertas predefinidas")
        ofertas = [
            Oferta("Naturgy actual 2026",
                   kwh_unico=0.144972, pot_unica=False, pot_p1=0.110283, pot_p2=0.033469,
                   excedente=0.07, bateria_virtual=True,
                   notas="Lo que tienes ahora"),
            Oferta("Naturgy oferta",
                   kwh_unico=0.1449, pot_unica=False, pot_p1=0.1102, pot_p2=0.033,
                   excedente=0.07, bateria_virtual=True,
                   notas="Casi igual que actual — no merece el trámite"),
            Oferta("TotalEnergies pot.0075",
                   kwh_unico=0.1099, pot_unica=True, pot_unico=0.075,
                   excedente=0.07, bateria_virtual=False,
                   notas="Mejor factura mensual pero sin batería virtual"),
            Oferta("Repsol Solar Fijo",
                   kwh_unico=0.1299, pot_unica=True, pot_unico=0.0819,
                   excedente=0.06, bateria_virtual=False),
            Oferta("Holaluz variable",
                   kwh_unico=0.141, pot_unica=True, pot_unico=0.082,
                   excedente=0.06, bateria_virtual=True),
            Oferta("Endesa oferta",
                   kwh_unico=0.148828, pot_unica=True, pot_unico=2.7444/30.4375,
                   excedente=0.06, bateria_virtual=False),
            Oferta("Octopus DH",
                   dh=True, kwh_punta=0.245, kwh_llano=0.155, kwh_valle=0.13,
                   pot_unica=False, pot_p1=0.097, pot_p2=0.030,
                   excedente=0.035, bateria_virtual=False,
                   notas="No apto sin desplazamiento de carga"),
            Oferta("TotalEnergies pot.1547",
                   kwh_unico=0.1099, pot_unica=True, pot_unico=0.1547,
                   excedente=0.07, bateria_virtual=False,
                   notas="RECHAZADA — potencia multiplicada x2"),
            Oferta("Naturgy plana 58€",
                   tarifa_plana=True, coste_fijo_anual=696,
                   excedente=0.0, bateria_virtual=False,
                   notas="RECHAZADA — inadecuada para solar"),
        ]

    # Modo: ranking, detalle o interactivo
    modo = sys.argv[1] if len(sys.argv) > 1 else "ranking"

    if modo == "ranking":
        imprimir_ranking(ofertas, verbose=False)

    elif modo == "detalle":
        imprimir_ranking(ofertas, verbose=True)

    elif modo == "nueva":
        nueva = nueva_oferta_interactiva()
        ofertas.append(nueva)
        d = calcular(nueva)
        print(f"\n─── RESULTADO: {nueva.nombre} ───")
        print(f"  Energía:         {d['energia']:>8.2f} €")
        print(f"  Excedentes:      {d['excedentes']:>8.2f} € (−)")
        print(f"  Potencia:        {d['potencia']:>8.2f} €")
        print(f"  Bono + contador: {d['otros']:>8.2f} €")
        print(f"  Imp. elec.:      {d['imp_elec']:>8.2f} €")
        print(f"  IVA 21%:         {d['iva']:>8.2f} €")
        print(f"  ─────────────────────────")
        print(f"  Factura anual:   {d['factura']:>8.2f} €  ({d['factura']/12:.2f} €/mes)")
        if nueva.bateria_virtual:
            print(f"  Bat. virtual:    {d['bat_virtual']:>8.2f} € (−)")
        print(f"  COSTE REAL:      {d['coste_real']:>8.2f} €/año  ({d['coste_real']/12:.2f} €/mes)")
        for alerta in alertas(nueva, d):
            print(f"\n  {alerta}")
        imprimir_ranking(ofertas, verbose=False)

    elif modo == "calcular":
        # Uso: python calculadora_tarifas.py calcular <kwh> <pot> <exc> [bat=s/n] [nombre]
        # Ejemplo: python calculadora_tarifas.py calcular 0.1099 0.075 0.07 n "Mi oferta"
        try:
            kwh  = float(sys.argv[2])
            pot  = float(sys.argv[3])
            exc  = float(sys.argv[4])
            bat  = len(sys.argv) > 5 and sys.argv[5].lower() == "s"
            nom  = sys.argv[6] if len(sys.argv) > 6 else "Oferta rápida"
            o    = Oferta(nom, kwh_unico=kwh, pot_unica=True, pot_unico=pot, excedente=exc, bateria_virtual=bat)
            d    = calcular(o)
            print(f"\n{nom}: {d['coste_real']:.0f} €/año  ({d['coste_real']/12:.2f} €/mes)")
            for alerta in alertas(o, d): print(f"  {alerta}")
            ofertas.append(o)
            imprimir_ranking(ofertas)
        except (IndexError, ValueError):
            print("Uso: python calculadora_tarifas.py calcular <kwh> <pot_dia> <exc> [s/n bat] [nombre]")
            print("Ej:  python calculadora_tarifas.py calcular 0.1099 0.075 0.07 n TotalEnergies")

    else:
        print("Modos disponibles:")
        print("  python calculadora_tarifas.py ranking       → ranking completo")
        print("  python calculadora_tarifas.py detalle       → ranking con desglose y alertas")
        print("  python calculadora_tarifas.py nueva         → introducir oferta por consola")
        print("  python calculadora_tarifas.py calcular <kwh> <pot> <exc> [bat] [nombre]")
