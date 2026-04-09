import streamlit as st
import pandas as pd
import numpy as np

# Configuración inicial de la página
st.set_page_config(page_title="Simulador Cargador con batería", layout="wide")

st.title("🔋 Simulación de Cargador EV con Batería Integrada vs. Directo a Red (24h)")

st.markdown("""
Esta herramienta simula el funcionamiento a lo largo de un día completo de un cargador eléctrico asistido por baterías y lo **compara directamente** contra un cargador convencional enlazado a la misma red sin apoyo de almacenamiento.
- **Potencia Máxima de Salida (Con Batería)**: 240 kW.
- **Potencia Máxima de Salida (Tradicional sin batería)**: 40 kW (límite de la propia red).
- **Mangueras Disponibles en ambos sistemas**: 2.
""")

st.sidebar.header("⚙️ Parámetros de la Instalación")
bateria_capacidad = st.sidebar.number_input("Capacidad Batería  (kWh)", value=180.0, step=10.0)
modo_descarga = st.sidebar.selectbox(
    "Estrategia de carga de vehículos",
    options=[
        "Solo Baterías (No Simultánea)",
        "Simultánea CON recarga de excedente",
        "Simultánea SIN recarga de excedente"
    ],
    index=1,
    help="Define el comportamiento al recargar vehículos. 'Solo Baterías': la red no aporta a los vehículos. 'Simultánea': la red aporta hasta 40kW a los vehículos, y el excedente (si la demanda es menor) puede o no usarse para cargar la batería simultáneamente."
)

st.sidebar.subheader("Dinámica Vehicular")
usar_tasa_por_hora = st.sidebar.checkbox("Configurar tasa de llegadas por hora", value=True)

if usar_tasa_por_hora:
    st.sidebar.write("Tasa de llegadas (veh/hora):")
    tasas_defecto = [0.0] * 24
    tasas_defecto[8] = 3.0
    tasas_defecto[12] = 1.0
    tasas_defecto[13] = 1.0
    tasas_defecto[14] = 1.0
    tasas_defecto[20] = 1.0
    
    df_horas_init = pd.DataFrame({
        "Hora": [f"{i:02d}:00" for i in range(24)],
        "Tasa": tasas_defecto
    })
    df_tasas = st.sidebar.data_editor(
        df_horas_init,
        hide_index=True,
        column_config={
            "Hora": st.column_config.TextColumn("Hora", disabled=True),
            "Tasa": st.column_config.NumberColumn("Tasa", min_value=0.0, max_value=20.0, step=0.1)
        }
    )
    tasas_llegadas_lista = df_tasas["Tasa"].tolist()
else:
    tasa_llegadas = st.sidebar.slider("Tasa de llegadas (vehículos/hora)", min_value=0.1, max_value=4.0, value=0.6, step=0.1)
    tasas_llegadas_lista = [tasa_llegadas] * 24

energia_por_ev = st.sidebar.slider("Energía media demandada por EV (kWh)", min_value=10.0, max_value=80.0, value=60.0, step=5.0)
potencia_por_ev = st.sidebar.slider("Potencia máxima admitida por el EV (kW)", min_value=50.0, max_value=240.0, value=150.0, step=10.0)

semilla = st.sidebar.slider("Semilla aleatoria (variar escenarios del día)", min_value=1, max_value=100, value=42)

def correr_simulacion():
    # Inicialización de 24h
    np.random.seed(semilla)
    minutos = 24 * 60
    
    # KPIs -> Sistema CON Batería
    energia_bateria = bateria_capacidad
    vehiculos_bat = []
    totales_bat = 0
    energia_entregada_bat = 0.0
    rechazados_bat = 0
    
    # KPIs -> Sistema SIN Batería (Directo a red)
    vehiculos_red = []
    totales_red = 0
    energia_entregada_red = 0.0
    rechazados_red = 0
    
    vehiculos_bat_terminados_hoy = 0
    vehiculos_red_terminados_hoy = 0
    
    tiempo_espera_acumulado_bat = 0.0
    tiempo_espera_acumulado_red = 0.0
    
    historial = []
    
    for t in range(minutos):
        hora_actual = t // 60
        prob_llegada = tasas_llegadas_lista[hora_actual] / 60.0
        
        # 1. Llegadas (Impacta en ambos universos matemáticos al mismo tiempo para puridad comparativa)
        if np.random.rand() < prob_llegada:
            e_demanda = np.random.uniform(energia_por_ev * 0.8, energia_por_ev * 1.2)
            p_demanda = np.random.uniform(potencia_por_ev * 0.8, potencia_por_ev * 1.2)
            
            # Admisión en sistema CON Batería 
            if len(vehiculos_bat) < 2:
                vehiculos_bat.append({'energia_restante': e_demanda, 'potencia_demanda': p_demanda})
                totales_bat += 1
            else:
                rechazados_bat += 1
                
            # Admisión en sistema SIN Batería Constante
            if len(vehiculos_red) < 2:
                vehiculos_red.append({'energia_restante': e_demanda, 'potencia_demanda': p_demanda})
                totales_red += 1
            else:
                rechazados_red += 1

        # ==========================================
        # 2. Dinámica de Trabajo: Sistema CON BATERÍA 
        # ==========================================
        p_entregada_bat_esta_ronda = 0.0
        p_red_bat = 0.0
        
        if len(vehiculos_bat) > 0:
            demanda_total = sum(v['potencia_demanda'] for v in vehiculos_bat)
            
            # El inversor exprime hasta un máximo de 240 kW a los EVs conectados
            p_entregada_bat_esta_ronda = min(demanda_total, 240.0)
            
            if modo_descarga in ["Simultánea CON recarga de excedente", "Simultánea SIN recarga de excedente"]:
                p_red_aporte_ev = min(p_entregada_bat_esta_ronda, 40.0)
                p_bat_aporte_ev = p_entregada_bat_esta_ronda - p_red_aporte_ev
                
                # Freno de emergencia por batería agotada
                p_bat_aporte_ev = min(p_bat_aporte_ev, energia_bateria * 60.0)
                
                p_entregada_bat_esta_ronda = p_red_aporte_ev + p_bat_aporte_ev
                energia_bateria -= (p_bat_aporte_ev / 60.0)
                
                potencia_sobrante_red = 40.0 - p_red_aporte_ev
                
                if modo_descarga == "Simultánea CON recarga de excedente" and potencia_sobrante_red > 0 and energia_bateria < bateria_capacidad:
                    energia_que_cabe = bateria_capacidad - energia_bateria
                    p_carga_bat = min(potencia_sobrante_red, energia_que_cabe * 60.0)
                    energia_bateria += (p_carga_bat / 60.0)
                    p_red_bat = p_red_aporte_ev + p_carga_bat
                else:
                    p_red_bat = p_red_aporte_ev
            else:
                if energia_bateria > 0.5:
                    p_entregada_bat_esta_ronda = min(p_entregada_bat_esta_ronda, energia_bateria * 60.0)
                    energia_bateria -= (p_entregada_bat_esta_ronda / 60.0)
                else:
                    p_entregada_bat_esta_ronda = 0.0
                    if energia_bateria < bateria_capacidad:
                        p_red_bat = 40.0
                        energia_bateria = min(bateria_capacidad, energia_bateria + (p_red_bat / 60.0))
            
            if p_entregada_bat_esta_ronda > 0:
                for v in vehiculos_bat:
                    porcion = p_entregada_bat_esta_ronda * (v['potencia_demanda'] / demanda_total)
                    energia_recibida = porcion / 60.0
                    v['energia_restante'] -= energia_recibida
                    energia_entregada_bat += energia_recibida
            
            vehiculos_bat_next = [v for v in vehiculos_bat if v['energia_restante'] > 0.01]
            vehiculos_bat_terminados_hoy += (len(vehiculos_bat) - len(vehiculos_bat_next))
            vehiculos_bat = vehiculos_bat_next
        else:
            # Reconexión para carga de batería
            if energia_bateria < bateria_capacidad:
                p_red_bat = 40.0
                energia_bateria = min(bateria_capacidad, energia_bateria + (p_red_bat / 60.0))
                
        # ==========================================
        # 3. Dinámica de Trabajo: Sistema TRADICIONAL (Sin Batería)
        # ==========================================
        p_entregada_red_total = 0.0
        if len(vehiculos_red) > 0:
            demanda_total_red = sum(v['potencia_demanda'] for v in vehiculos_red)
            # Como no hay buffer, el límite infranqueable es la acometida dictada (40 kW continuos)
            p_entregada_red_total = min(demanda_total_red, 40.0)
            
            for v in vehiculos_red:
                porcion = p_entregada_red_total * (v['potencia_demanda'] / demanda_total_red)
                energia_recibida = porcion / 60.0
                v['energia_restante'] -= energia_recibida
                energia_entregada_red += energia_recibida
                
            vehiculos_red_next = [v for v in vehiculos_red if v['energia_restante'] > 0.01]
            vehiculos_red_terminados_hoy += (len(vehiculos_red) - len(vehiculos_red_next))
            vehiculos_red = vehiculos_red_next

        tiempo_espera_acumulado_bat += len(vehiculos_bat)
        tiempo_espera_acumulado_red += len(vehiculos_red)

        historial.append({
            'Tiempo (Hora)': t / 60.0,
            'SoC Batería (%)': (energia_bateria / bateria_capacidad) * 100.0,
            'Potencia Con Batería  (kW)': p_entregada_bat_esta_ronda,
            'Potencia Red  (kW)': p_red_bat,
            'Potencia Sin Batería Tradicional (kW)': p_entregada_red_total,
            'Mangueras Ocupadas CON': len(vehiculos_bat),
            'Mangueras Ocupadas SIN': len(vehiculos_red),
            'Energía Entregada CON (kWh)': energia_entregada_bat,
            'Energía Entregada SIN (kWh)': energia_entregada_red,
            'Vehículos Completados CON': vehiculos_bat_terminados_hoy,
            'Vehículos Completados SIN': vehiculos_red_terminados_hoy,
            'Tiempo Acumulado CON (min)': tiempo_espera_acumulado_bat,
            'Tiempo Acumulado SIN (min)': tiempo_espera_acumulado_red
        })
        
    df = pd.DataFrame(historial)
    
    res = {
        'bat': {'totales': totales_bat, 'rechazados': rechazados_bat, 'energia': energia_entregada_bat, 'tiempo_medio': (tiempo_espera_acumulado_bat / totales_bat) if totales_bat > 0 else 0},
        'red': {'totales': totales_red, 'rechazados': rechazados_red, 'energia': energia_entregada_red, 'tiempo_medio': (tiempo_espera_acumulado_red / totales_red) if totales_red > 0 else 0}
    }
    return df, res

df, res = correr_simulacion()

# Métricas Comparativas
st.markdown("### 🏆 Comparativa de Rendimiento del Servicio (Jornada 24 Horas) ")

col1, col2 = st.columns(2)

with col1:
    st.info("#### 🟢 Solución  (Con Batería)")
    st.metric("EVs Recargados Satisfactoriamente", res['bat']['totales'])
    st.metric("Pérdida de Clientes (Cola Larga)", res['bat']['rechazados'], delta_color="inverse")
    st.metric("Total Energía Despachada", f"{res['bat']['energia']:.1f} kWh")
    st.metric("Pico Carga Hacia Vehículos", f"{df['Potencia Con Batería  (kW)'].max():.1f} kW", delta="Alta Potencia")
    st.metric("Tiempo Medio Carga/Vehículo", f"{res['bat']['tiempo_medio']:.1f} min")

with col2:
    st.warning("#### 🔴 Cargador Directo Convencional (Constante a 40 kW)")
    st.metric("EVs Recargados Satisfactoriamente", res['red']['totales'])
    st.metric("Pérdida de Clientes (Cola Larga)", res['red']['rechazados'], delta_color="inverse")
    st.metric("Total Energía Despachada", f"{res['red']['energia']:.1f} kWh")
    st.metric("Pico Carga Hacia Vehículos", f"{df['Potencia Sin Batería Tradicional (kW)'].max():.1f} kW")
    st.metric("Tiempo Medio Carga/Vehículo", f"{res['red']['tiempo_medio']:.1f} min")


st.markdown("---")
df_graficos = df.set_index('Tiempo (Hora)')

# Gráfico 1: Entrega de potencia
st.subheader("⚡ 1. Velocidad de Entrega de Potencia a Vehículos (kW)")
st.caption("Nota cómo el modelo  entrega repuntes tremendos de tensión completando las operaciones de manera fugaz.")
st.line_chart(df_graficos[['Potencia Con Batería  (kW)', 'Potencia Sin Batería Tradicional (kW)']])

# Gráfico 2: Intercambio 
st.subheader("🔄 2. Detalle Intercambio  (Red vs. Entregada)")
st.caption("Ilustra la utilización de la red eléctrica para recargar la batería (o ayudar a recargar vehículos) comparado con la potencia entregada a los vehículos.")
st.area_chart(df_graficos[['Potencia Con Batería  (kW)', 'Potencia Red  (kW)']])

# Gráfico 3: Colapso vs Fluidez
st.subheader("🚗 3. Ocupación de la Estación (Mangueras Activas simultáneas)")
st.caption("En la modalidad sin batería los vehículos pasan incontables horas reteniendo ambos cables. Mangueras al máximo = Clientes Rechazados.")
st.line_chart(df_graficos[['Mangueras Ocupadas CON', 'Mangueras Ocupadas SIN']])

# Gráfico 4: Estado de Carga Batería
st.subheader("🔋 4. Vida y Desgaste del Estado de Carga de las Baterías  (SoC %)")
st.line_chart(df_graficos['SoC Batería (%)'], color="#2ecc71")

# Gráfico 5: Vehículos Cargados (Evolución)
st.subheader("🏁 5. Evolución de Vehículos Completados")
st.caption("Muestra la cantidad acumulada de EVs que han finalizado su recarga.")
st.line_chart(df_graficos[['Vehículos Completados CON', 'Vehículos Completados SIN']])

# Gráfico 6: Energía Entregada (Acumulada)
st.subheader("📈 6. Energía Total Entregada a Vehículos (kWh)")
st.caption("Comparativa de la cantidad total de energía volcada hacia los coches a lo largo del día.")
st.line_chart(df_graficos[['Energía Entregada CON (kWh)', 'Energía Entregada SIN (kWh)']])

# Gráfico 7: Tiempo de Carga Acumulado
st.subheader("⏱️ 7. Tiempo de Estancia Acumulado por Vehículos (Minutos)")
st.caption("Evolución del tiempo total invertido por todos los vehículos en la estación. Una pendiente más pronunciada indica que los coches pasan un tiempo mayor ocupando los cargadores.")
st.line_chart(df_graficos[['Tiempo Acumulado CON (min)', 'Tiempo Acumulado SIN (min)']])
