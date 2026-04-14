"""
DevBuddy Dashboard - Version simplifiée qui fonctionne
"""

import streamlit as st
import json
import time
from pathlib import Path
from datetime import datetime
import os

# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="DevBuddy Dashboard",
    page_icon="🧠",
    layout="wide"
)

STATE_FILE = Path("devbuddy_current_state.json")
LOG_FILE = Path("devbuddy_interventions.json")

# ============================================================
# AUTO-REFRESH (toutes les 3 secondes)
# ============================================================

st.markdown('<meta http-equiv="refresh" content="3">', unsafe_allow_html=True)

# ============================================================
# TITRE
# ============================================================

st.title("🧠 DevBuddy Dashboard")
st.caption("Agent de protection mentale pour développeurs")

# ============================================================
# FONCTIONS SIMPLES
# ============================================================

def load_state():
    """Charge l'état avec gestion d'erreur"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def load_logs():
    """Charge les logs avec gestion d'erreur"""
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

# ============================================================
# AFFICHAGE
# ============================================================

state = load_state()
logs = load_logs()

# Afficher le chemin des fichiers pour déboguer
st.sidebar.header("📁 Débogage")
st.sidebar.write(f"**Dossier actuel :** {Path.cwd()}")
st.sidebar.write(f"**Fichier état :** {STATE_FILE.absolute()}")
st.sidebar.write(f"**Fichier logs :** {LOG_FILE.absolute()}")
st.sidebar.write(f"**État existe :** {'✅ OUI' if STATE_FILE.exists() else '❌ NON'}")
st.sidebar.write(f"**Logs existe :** {'✅ OUI' if LOG_FILE.exists() else '❌ NON'}")

# Créer des fichiers de test si besoin
if st.sidebar.button("🧪 Créer données de test"):
    test_state = {
        "timestamp": datetime.now().isoformat(),
        "active_window": "Visual Studio Code - test",
        "is_working": True,
        "is_stressed": False,
        "consecutive_work_minutes": 45,
        "hour_of_day": datetime.now().hour,
        "day_of_week": datetime.now().strftime("%A"),
        "screen_time_today_minutes": 120,
        "agent_running": True,
        "action_taken": "test",
        "last_intervention": "Ceci est un test"
    }
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(test_state, f, indent=2)
    
    test_logs = [
        {
            "timestamp": datetime.now().isoformat(),
            "action": "notify",
            "reason": "Test",
            "message": "🧪 Notification de test - Tout fonctionne !"
        }
    ]
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(test_logs, f, indent=2)
    
    st.sidebar.success("Données de test créées !")
    time.sleep(1)
    st.rerun()

st.sidebar.divider()
st.sidebar.header("📊 Stats fichiers")

# Vérifier le contenu
if STATE_FILE.exists():
    size = STATE_FILE.stat().st_size
    st.sidebar.write(f"Taille état : {size} octets")
if LOG_FILE.exists():
    size = LOG_FILE.stat().st_size
    st.sidebar.write(f"Taille logs : {size} octets")

# ============================================================
# ZONE PRINCIPALE
# ============================================================

col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 État Actuel")
    
    if state:
        agent_running = state.get("agent_running", False)
        
        if agent_running:
            st.success("✅ Agent ACTIF")
        else:
            st.warning("⚠️ Agent INACTIF")
        
        st.metric("Application", state.get("active_window", "N/A")[:40])
        st.metric("Travail consécutif", f"{state.get('consecutive_work_minutes', 0)} min")
        st.metric("Heure", f"{state.get('hour_of_day', 0)}h")
        st.metric("Jour", state.get("day_of_week", "N/A"))
        st.metric("Temps d'écran", f"{state.get('screen_time_today_minutes', 0)//60}h{state.get('screen_time_today_minutes', 0)%60:02d}")
        
        if state.get("is_working"):
            st.info("💼 Mode travail")
        if state.get("is_stressed"):
            st.warning("⚠️ Stress détecté")
        
        action = state.get("action_taken", "")
        if action and action != "none":
            st.text(f"Dernière action : {action}")
        
        # Afficher les données brutes pour déboguer
        with st.expander("🔍 Données brutes (débogage)"):
            st.json(state)
    else:
        st.error("❌ Aucune donnée disponible")
        st.info("""
        **Solutions :**
        1. Lance l'agent : `python agent_service.py`
        2. Ou clique sur "Créer données de test" dans la sidebar
        """)

with col2:
    st.subheader("📜 Dernières interventions")
    
    if logs:
        for log in reversed(logs[-5:]):
            with st.container():
                st.markdown(f"**{log.get('timestamp', '')[:16]}**")
                st.markdown(f"*Action : {log.get('action', 'unknown')}*")
                st.markdown(f"Raison : {log.get('reason', 'N/A')}")
                st.markdown(f"Message : {log.get('message', '')[:80]}")
                st.divider()
        
        with st.expander("🔍 Logs bruts (débogage)"):
            st.json(logs)
    else:
        st.info("Aucune intervention pour l'instant")

# ============================================================
# INSTRUCTIONS
# ============================================================

st.divider()
st.markdown("""
### 📋 Instructions

1. **Lancer l'agent** (dans un terminal séparé) :
   ```powershell
   python agent_service.py""")