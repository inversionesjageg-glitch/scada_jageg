# Conflictos de direccion fisica detectados en el export de WinCC

Estas direcciones tienen **dos o mas nombres reales distintos** apuntando al
mismo byte del PLC. No es basura de exportacion (ya se filtraron los tags sin
nombre asignado). Ambos quedaron sembrados en la base de datos como
`is_simulated=True`, pero alguien con conocimiento de la logica del PLC
(Xavier) debe confirmar cual nombre es el vigente para desactivar/renombrar el otro.

| Direccion fisica | Nombres en conflicto |
|---|---|
| `DB1.DBW0` | `VARIABLE_1`, `VARIABLE_1_2`, `VARIABLE_1_3`, `VARIABLE_2` |
| `DB12.DBD26` | `ERROR_Z1_CO_EXT_S1`, `ERROR_ZONA_1_EXT_M` |
| `DB13.DBD26` | `ERROR_Z2_CO_EXT_S1`, `ERROR_ZONA_2_EXT_M` |
| `DB14.DBD26` | `ERROR_Z3CO_EXT_S1`, `ERROR_ZONA_3_EXT_M` |
| `DB15.DBD26` | `ERROR_Z4_CO_EXT_S1`, `ERROR_ZONA_4_EXT_M` |
| `DB16.DBD26` | `ERROR_Z5_CO_EXT_S1`, `ERROR_ZONA_5_EXT_M` |
| `DB17.DBD26` | `ERROR_RONG_BODY_S1`, `ERROR_ZONA_6_EXT_M` |
| `DB19.DBD26` | `ERROR_Z2_EXT_S2`, `ERROR_M_FILTER_M` |
| `DB20.DBD26` | `ERROR_Z3_EXT_S2`, `ERROR_SPIN_PP_M` |
| `DB21.DBD26` | `ERROR_Z4_EXT_S2`, `ERROR_ZONA_1_BAJANTE_M` |
| `DB22.DBD26` | `ERROR_Z5_EXT_S2`, `ERROR_ZONA_2_BAJANTE_M` |
| `DB23.DBD26` | `ERROR_Z6_EXT_S2`, `ERROR_ZONA_3_BAJANTE_M` |
| `DB24.DBD26` | `ERROR_Z1_CO_EXT_S2`, `ERROR_ZONA_4_BAJANTE_M` |
| `DB25.DBD26` | `ERROR_Z2_CO_EXT_S2`, `ERROR_ZONA_5_BAJANTE_M` |
| `DB27.DBD26` | `ERROR_Z4_CO_EXT_S2`, `ERROR_ZONA_6_BAJANTE_M` |
| `DB28.DBD52` | `INTEGRAL_Z5_CO_EXT_S2`, `PROPORTIONAL_Z5_CO_EXT_S2_0` |
| `DB30.DBD48` | `INTEGRAL_R_GRAFITO`, `PROPORTIONAL_R_GRAFITO` |
| `DB33.DBD114` | `PV_MP_EXTD_Z6_6`, `SP_M_FILTER` |
| `DB33.DBW152` | `PV_FILTERS_EX_PRESS`, `SV2_FILTERS_EX_PRESS_0` |