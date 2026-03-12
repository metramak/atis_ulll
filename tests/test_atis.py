"""
Тесты для ATIS генератора.
Запуск: pytest tests/ -v
"""
import sys
import pathlib

# Корень проекта — чтобы находились airports.py и tables.py
ROOT = pathlib.Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

# FastAPI нужен только для запуска сервера, не для бизнес-логики.
# Мокаем его чтобы тесты работали без установленного пакета.
try:
    import fastapi  # noqa: F401 — если установлен, используем как есть
except ModuleNotFoundError:
    from unittest.mock import MagicMock
    for mod in ['fastapi', 'fastapi.responses', 'fastapi.staticfiles',
                'fastapi.middleware', 'fastapi.middleware.cors']:
        sys.modules[mod] = MagicMock()
    sys.modules['fastapi'].Query = lambda *a, **kw: None

import main as _main
from main import (
    parse_metar,
    build_atis,
    auto_transition_level as auto_tl,
    load_config,
    save_config,
)


# ── METAR парсинг ────────────────────────────────────────────────────────────

def test_parse_cavok():
    md = parse_metar("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG", "ULLI")
    assert md['cavok'] is True
    assert md['qnh'] == '1027'
    assert md['wind'] is not None

def test_parse_wind_mps():
    md = parse_metar("ULLI 071000Z 27006MPS 9999 FEW030 05/01 Q1020 NOSIG", "ULLI")
    assert '270' in md['wind'] or 'DEGREES' in md['wind']
    assert '6' in md['wind']

def test_parse_variable_wind():
    md = parse_metar("ULAA 091000Z 20003MPS 150V240 9999 -SN OVC016 M12/M15 Q1019 NOSIG", "ULAA")
    assert 'VARIABLE' in md['wind']

def test_parse_vrb_wind():
    md = parse_metar("ULLI 071000Z VRB02MPS CAVOK 10/05 Q1015 NOSIG", "ULLI")
    assert 'VARIABLE' in md['wind']

def test_parse_weather():
    md = parse_metar("ULLI 071000Z 27004MPS 3000 -SN BKN010 M02/M05 Q1010 NOSIG", "ULLI")
    assert 'SNOW' in md['weather']
    assert 'LIGHT' in md['weather']

def test_parse_qfe():
    md = parse_metar("METAR ULAA 091000Z 20003MPS 9999 -SN OVC016 M12/M15 Q1019 NOSIG RMK QFE762/1017", "ULAA")
    assert md['qfe_mmhg'] == '762'
    assert md['qfe_hpa'] == '1017'

def test_parse_qfe_no_hpa():
    md = parse_metar("ULAA 091000Z 20003MPS 9999 OVC016 M12/M15 Q1019 NOSIG RMK QFE762", "ULAA")
    assert md['qfe_mmhg'] == '762'
    assert md.get('qfe_hpa') is None

def test_parse_rwy_state():
    md = parse_metar("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 R28L/290335 NOSIG", "ULLI")
    assert len(md['rwy_states']) == 1
    assert md['rwy_states'][0]['rwy'] == '28L'

def test_parse_rwy_state_clrd():
    md = parse_metar("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 R24/CLRD63 NOSIG", "ULLI")
    assert len(md['rwy_states']) == 1
    s = md['rwy_states'][0]
    assert s['rwy'] == '24'
    assert 'DRY' in s['deposit']

def test_parse_trend_nosig():
    md = parse_metar("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG", "ULLI")
    assert md['trend'] == 'NOSIG'

def test_parse_visibility():
    md = parse_metar("ULLI 071000Z 28004MPS 0800 FG OVC002 01/M01 Q1015 NOSIG", "ULLI")
    assert '800' in md['visibility'] or 'METERS' in md['visibility']


# ── ATIS генерация ───────────────────────────────────────────────────────────

def _atis(metar_str, icao="ULLI", arr="28L", dep="28R", app="ILS",
          tl=None, voice=False, **kwargs):
    md = parse_metar(metar_str, icao)
    eff_tl = tl or auto_tl(icao, md.get('qnh'))
    defaults = dict(lvp=False, birds=False, slippery=False, reduced_min=False,
                    closed_rwy=None, closed_twy=None, simult=None, segregated=False,
                    min_rwy_occup=False, dep_freq=None, remarks=None, freetext=None,
                    pressure_type="QNH")
    defaults.update(kwargs)
    return build_atis(icao=icao, info="A", metar_data=md, arr=arr, dep=dep,
                      app=app, tl=eff_tl, voice=voice, **defaults)

def test_atis_contains_airport_name():
    r = _atis("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG")
    assert 'PULKOVO' in r

def test_atis_contains_qnh():
    r = _atis("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG")
    assert 'QNH 1027' in r

def test_atis_qfe_appended_after_qnh():
    r = _atis("ULAA 091000Z 20003MPS 9999 -SN OVC016 M12/M15 Q1019 NOSIG RMK QFE762/1017",
              icao="ULAA", arr="26", dep="26")
    assert r.index('QFE') > r.index('QNH')

def test_atis_qfe_before_acknowledge():
    r = _atis("ULAA 091000Z 20003MPS 9999 -SN OVC016 M12/M15 Q1019 NOSIG RMK QFE762/1017",
              icao="ULAA", arr="26", dep="26")
    assert r.index('QFE') < r.index('ACKNOWLEDGE')

def test_atis_z_suffix_text():
    r = _atis("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG", arr="28L")
    assert 'ILS APPROACH Z' in r or 'ILS Z' in r

def test_atis_no_z_suffix_other_rwy():
    r = _atis("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG", arr="28R")
    assert 'ILS Z' not in r

def test_atis_voice_spells_digits():
    r = _atis("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG", voice=True)
    assert 'ONE ZERO TWO SEVEN' in r

def test_atis_voice_zulu_suffix():
    r = _atis("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG", arr="28L", voice=True)
    assert 'ZULU' in r

def test_atis_acknowledge_last():
    r = _atis("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG")
    assert 'ACKNOWLEDGE INFORMATION' in r

def test_atis_transition_level_auto():
    r = _atis("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG")
    assert 'TRANSITION LEVEL 50' in r

def test_atis_lvp_flag():
    r = _atis("ULLI 071000Z 28006MPS CAVOK 03/M01 Q1027 NOSIG", lvp=True)
    assert 'LOW VISIBILITY' in r

def test_atis_ulaa():
    r = _atis("METAR ULAA 091000Z 20003MPS 9999 -SN OVC016 M12/M15 Q1019 NOSIG RMK QFE762/1017",
              icao="ULAA", arr="26", dep="26")
    assert 'ARKHANGELSK' in r
    assert 'QFE' in r


# ── Конфиг ───────────────────────────────────────────────────────────────────

def test_config_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(_main, 'CONFIG_FILE', tmp_path / 'config.json')
    save_config({'app': 'RNP', 'remarks': 'ULAA test'}, 'ULAA')
    save_config({'app': 'ILS', 'remarks': 'ULLI test'}, 'ULLI')

    cfg_ulaa = load_config('ULAA')
    cfg_ulli = load_config('ULLI')

    assert cfg_ulaa['remarks'] == 'ULAA test'
    assert cfg_ulli['remarks'] == 'ULLI test'
    assert cfg_ulaa['remarks'] != cfg_ulli['remarks']

def test_config_unknown_airport_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(_main, 'CONFIG_FILE', tmp_path / 'config.json')
    cfg = load_config('XXXX')
    assert cfg['icao'] == 'XXXX'
    assert cfg['remarks'] == ''