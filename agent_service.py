"""
Agent DevBuddy - Service d'arrière-plan AVEC ACTIONS FORTES
Peut bloquer des apps, verrouiller l'écran, forcer des pauses.
Avec un system prompt complet pour une personnalité cohérente.
"""

import os
import time
import json
import subprocess
import ctypes
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict

import psutil
import win32gui
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CONFIGURATION GLOBALE
# ============================================================

SHARED_STATE_FILE = Path("devbuddy_current_state.json")
INTERVENTION_LOG_FILE = Path("devbuddy_interventions.json")
SYSTEM_PROMPT_FILE = Path("system_prompt.txt")

# ============================================================
# MODE TEST (SIMULATION D'HEURE)
# ============================================================

TEST_MODE = True           # ← True pour tester, False pour heure réelle
SIMULATED_HOUR = 23        # ← Heure simulée (23h, 1h, etc.)
SIMULATED_MINUTE = 30      # ← Minute simulée

# ============================================================
# SYSTEM PROMPT (Personnalité de l'agent)
# ============================================================

DEFAULT_SYSTEM_PROMPT = """Tu es DevBuddy, un agent de protection mentale pour développeurs et ingénieurs.

TON RÔLE :
Tu interviens quand l'utilisateur travaille trop longtemps ou trop tard.
Tu dois le protéger du burnout et du surmenage.

TA PERSONNALITÉ :
- Tu parles comme un administrateur système bienveillant mais ferme
- Tu utilises des analogies techniques (serveur, CPU, RAM, cache, build, deploy, kernel panic)
- Tu es direct et concis, pas de longs discours
- Tu donnes des instructions claires comme des commandes terminal

TON TON :
- Bienveillant mais autoritaire quand nécessaire
- Pas de "respire un grand coup" ou "tout va bien se passer"
- Plutôt "Arrêt du service recommandé" ou "Build en échec, pause requise"

EXEMPLES DE RÉPONSES :
- "CPU à 95% depuis 2h. Thermal throttling activé. Pause obligatoire."
- "Serveur de travail hors plage horaire. Shutdown recommandé."
- "Merge conflict détecté entre travail et vie perso. Resolve now."
- "Build failed : fatigue excessive. Rebuild après 10min de pause."
- "Mémoire saturée. Garbage collector activé. Déconnexion requise."

RÈGLES ABSOLUES :
- Maximum 2 phrases
- Une analogie technique par message
- En français uniquement
- Direct et utile, jamais vague"""

def load_system_prompt():
    """Charge le system prompt depuis un fichier ou utilise le défaut"""
    if SYSTEM_PROMPT_FILE.exists():
        with open(SYSTEM_PROMPT_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        with open(SYSTEM_PROMPT_FILE, 'w', encoding='utf-8') as f:
            f.write(DEFAULT_SYSTEM_PROMPT)
        return DEFAULT_SYSTEM_PROMPT

# ============================================================
# ÉTAT PARTAGÉ
# ============================================================

@dataclass
class DevState:
    timestamp: str
    active_window: str
    is_working: bool
    is_stressed: bool
    consecutive_work_minutes: int
    hour_of_day: int
    day_of_week: str
    screen_time_today_minutes: int
    agent_running: bool = True
    last_intervention: str = ""
    action_taken: str = ""

# ============================================================
# ACTIONS FORTES
# ============================================================

class ActionExecutor:
    """Exécute des actions concrètes sur le système"""
    
    def __init__(self):
        self.forced_break_active = False
        self.break_start_time = None
        
        # Applications à bloquer (noms de processus)
        self.blocked_apps = [
            # Éditeurs
            "code.exe", "pycharm64.exe", "idea64.exe", "webstorm64.exe",
            "sublime_text.exe", "notepad++.exe",
            # Communication
            "slack.exe", "teams.exe", "zoom.exe", "outlook.exe",
            "discord.exe", "skype.exe",
            # Terminaux
            "powershell.exe", "cmd.exe", "windowsterminal.exe",
        ]
        
    def send_notification(self, title: str, message: str, duration: int = 10):
        """Notification Windows via PowerShell (compatible Python 3.13)"""
        try:
            ps_script = f'''
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
            
            $template = @"
            <toast>
                <visual>
                    <binding template="ToastGeneric">
                        <text>{title}</text>
                        <text>{message}</text>
                    </binding>
                </visual>
            </toast>
            "@
            
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template)
            $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("DevBuddy").Show($toast)
            '''
            
            subprocess.run(["powershell", "-Command", ps_script], capture_output=True)
            print(f"  📢 Notification: {message[:50]}...")
            
        except Exception as e:
            print(f"  ⚠️ Erreur notification: {e}")
            # Fallback console
            print(f"\n{'='*50}")
            print(f"🧠 DevBuddy - {title}")
            print(f"{message}")
            print(f"{'='*50}\n")
    
    def show_break_timer(self, minutes: int = 10):
        """Affiche une popup de pause forcée"""
        message = f"DevBuddy - PAUSE FORCEE{chr(10)}{chr(10)}Tu travailles depuis trop longtemps.{chr(10)}Pause obligatoire de {minutes} minutes.{chr(10)}{chr(10)}Leve-toi, bois de l'eau, regarde par la fenetre."
        
        try:
            subprocess.Popen(['msg', '*', message], shell=True)
        except:
            try:
                subprocess.Popen([
                    'powershell', '-Command',
                    f'Add-Type -AssemblyName System.Windows.Forms; '
                    f'[System.Windows.Forms.MessageBox]::Show("{message}", "DevBuddy - Pause Forcée")'
                ], shell=True)
            except:
                pass
        
        self.forced_break_active = True
        self.break_start_time = datetime.now()
        
    def block_work_applications(self) -> int:
        """Ferme toutes les applications de travail"""
        killed_count = 0
        
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() in [b.lower() for b in self.blocked_apps]:
                    proc.kill()
                    killed_count += 1
                    print(f"  🚫 Fermé: {proc.info['name']}")
            except:
                pass
        
        if killed_count > 0:
            self.send_notification(
                "🧠 DevBuddy - Action Forte",
                f"🚫 {killed_count} application(s) professionnelle(s) fermée(s). Il est tard, repose-toi.",
                duration=15
            )
        
        return killed_count
    
    def lock_screen(self):
        """Verrouille l'écran Windows"""
        self.send_notification(
            "🧠 DevBuddy - Action Forte",
            "🔒 Écran verrouillé. C'est l'heure de déconnecter.",
            duration=10
        )
        time.sleep(2)
        ctypes.windll.user32.LockWorkStation()
    
    def force_sleep(self):
        """Met l'ordinateur en veille"""
        self.send_notification(
            "🧠 DevBuddy - Action Critique",
            "😴 Mise en veille forcée. Bonne nuit !",
            duration=5
        )
        time.sleep(3)
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

# ============================================================
# CAPTEURS
# ============================================================

def get_active_window_title() -> str:
    """Récupère le titre de la fenêtre active"""
    try:
        window = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(window).lower()
    except:
        return ""

class EnvironmentSensor:
    """Analyse l'environnement du développeur"""
    
    def __init__(self):
        self.session_start = datetime.now()
        self.last_break = datetime.now()
        
        # Applications considérées comme "travail"
        self.work_keywords = [
            'brave', 'chrome', 'edge', 'firefox', 'opera',
            'word', 'microsoft word', 'winword', 'excel', 'powerpoint',
            'onenote', 'notepad', 'bloc-notes', 'document',
            'visual studio code', 'vscode', 'pycharm', 'intellij',
            'webstorm', 'phpstorm', 'sublime', 'notepad++', 'code',
            'terminal', 'powershell', 'cmd', 'git bash', 'administrateur',
            'slack', 'teams', 'zoom', 'jira', 'outlook', 'gmail',
            'meet', 'discord', 'webex', 'skype',
            'python', 'docker', 'postman', 'git', 'github', 'figma'
        ]
        
        self.stress_keywords = [
            'slack', 'teams', 'zoom', 'jira', 'outlook', 'meet', 'discord'
        ]
    
    def analyze_window(self, title: str) -> dict:
        title_lower = title.lower()
        is_working = any(kw in title_lower for kw in self.work_keywords)
        is_stressed = any(kw in title_lower for kw in self.stress_keywords)
        return {"is_working": is_working, "is_stressed": is_stressed}
    
    def get_current_state(self) -> DevState:
        now = datetime.now()
        active_window = get_active_window_title()
        analysis = self.analyze_window(active_window)
        
        if analysis["is_working"]:
            consecutive = (now - self.last_break).total_seconds() / 60
        else:
            if (now - self.last_break).total_seconds() > 120:
                self.last_break = now
            consecutive = 0
        
        # ✅ Gestion du mode test
        if TEST_MODE:
            current_hour = SIMULATED_HOUR
            simulated_time = now.replace(hour=SIMULATED_HOUR, minute=SIMULATED_MINUTE)
        else:
            current_hour = now.hour
            simulated_time = now
        
        return DevState(
            timestamp=simulated_time.isoformat(),
            active_window=active_window[:100] if active_window else "Aucune",
            is_working=analysis["is_working"],
            is_stressed=analysis["is_stressed"],
            consecutive_work_minutes=int(consecutive),
            hour_of_day=current_hour,
            day_of_week=now.strftime("%A"),
            screen_time_today_minutes=int((now - self.session_start).total_seconds() / 60),
            agent_running=True
        )

# ============================================================
# CERVEAU (DÉCISIONS + IA)
# ============================================================

class AgentBrain:
    """Prend les décisions et communique avec l'IA"""
    
    def __init__(self):
        self.client = InferenceClient(
            model="Qwen/Qwen2.5-7B-Instruct",
            token=os.getenv("HUGGINGFACE_API_KEY")
        )
        self.last_intervention_time = datetime.now() - timedelta(hours=1)
        self.last_intervention_message = ""
        self.last_action = ""
        self.action_executor = ActionExecutor()
        self.system_prompt = load_system_prompt()
        
    def decide_action(self, state: DevState) -> tuple[str, str]:
        """
        Décide quelle action prendre
        Retourne (type_action, raison)
        """
        
        # ============================================================
        # ✅ CONFIGURATION DES HEURES (CORRIGÉE)
        # ============================================================
        
        HOUR_BLOCK_APPS = 21      # 21h → Fermeture apps pro
        HOUR_LOCK_SCREEN = 23     # 23h → Verrouillage écran
        HOUR_FORCE_SLEEP = 1      # 1h du matin → Mise en veille
        
        DISABLE_NIGHT_ACTIONS = False  # ← True pour désactiver
        
        # ============================================================
        # ACTIONS NOCTURNES
        # ============================================================
        
        if not DISABLE_NIGHT_ACTIONS and state.is_working:
            
            # 🔴 NIVEAU CRITIQUE : Après 1h du matin → Mise en veille
            if state.hour_of_day >= HOUR_FORCE_SLEEP and state.hour_of_day < 5:
                if (datetime.now() - self.last_intervention_time).total_seconds() > 1800:
                    return "force_sleep", f"Travail après {HOUR_FORCE_SLEEP}h - Mise en veille forcée"
            
            # 🟠 NIVEAU ÉLEVÉ : Après 23h → Verrouillage écran
            elif state.hour_of_day >= HOUR_LOCK_SCREEN:
                if (datetime.now() - self.last_intervention_time).total_seconds() > 3600:
                    return "lock_screen", f"Travail après {HOUR_LOCK_SCREEN}h - Verrouillage de l'écran"
            
            # 🟡 NIVEAU MODÉRÉ : Après 21h → Fermeture apps pro
            elif state.hour_of_day >= HOUR_BLOCK_APPS:
                if (datetime.now() - self.last_intervention_time).total_seconds() > 1800:
                    return "block_apps", f"Travail après {HOUR_BLOCK_APPS}h - Fermeture des applications pro"
        
        # ============================================================
        # ACTIONS DE JOURNÉE (basées sur la durée)
        # ============================================================
        
        # 🟠 Travail > 3h non-stop → Verrouillage
        if state.consecutive_work_minutes > 180:
            if (datetime.now() - self.last_intervention_time).total_seconds() > 3600:
                return "lock_screen", "Travail non-stop > 3h - Pause obligatoire"
        
        # 🟡 Travail > 2h non-stop → Pause forcée
        if state.consecutive_work_minutes > 120:
            if (datetime.now() - self.last_intervention_time).total_seconds() > 1800:
                return "break_timer", f"Travail non-stop > 2h - Pause de 10min imposée"
        
        # 🟢 Travail > 90min non-stop → Notification
        if state.consecutive_work_minutes > 90:
            if (datetime.now() - self.last_intervention_time).total_seconds() > 900:
                return "notify", f"Travail non-stop depuis {state.consecutive_work_minutes} minutes"
        
        # 🟢 Apps de stress > 60min → Notification
        if state.is_stressed and state.consecutive_work_minutes > 60:
            if (datetime.now() - self.last_intervention_time).total_seconds() > 900:
                return "notify", "Exposition prolongée aux applications de communication"
        
        return "none", ""
    
    def generate_message(self, state: DevState, reason: str) -> str:
        """Génère un message personnalisé avec l'IA"""
        
        user_prompt = f"""Contexte actuel :
- Temps de travail consécutif : {state.consecutive_work_minutes} minutes
- Heure actuelle : {state.hour_of_day}h
- Application active : {state.active_window[:50]}
- Jour : {state.day_of_week}

Raison de l'intervention : {reason}

Génère une notification selon ta personnalité :"""
        
        try:
            response = self.client.chat_completion(
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=80,
                temperature=0.8
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"  ⚠️ Erreur IA: {e}")
            if state.hour_of_day >= 23:
                return "🚫 Serveur de travail hors plage horaire. Shutdown recommandé."
            elif state.consecutive_work_minutes > 120:
                return "⚠️ CPU en surchauffe. Thermal throttling activé. Pause obligatoire."
            else:
                return f"⚠️ {reason}. Protocole de pause activé."
    
    def execute_action(self, state: DevState, action_type: str, reason: str) -> str:
        """Exécute l'action décidée"""
        
        self.last_intervention_time = datetime.now()
        
        if action_type == "none":
            return ""
        
        elif action_type == "notify":
            message = self.generate_message(state, reason)
            self.action_executor.send_notification("🧠 DevBuddy", message)
            return message
        
        elif action_type == "break_timer":
            self.action_executor.show_break_timer(10)
            message = f"⏰ PAUSE FORCÉE : {reason}"
            self.action_executor.send_notification("🧠 DevBuddy - Action", message, duration=20)
            return message
        
        elif action_type == "block_apps":
            killed = self.action_executor.block_work_applications()
            message = f"🚫 {killed} applications professionnelles fermées. {reason}"
            return message
        
        elif action_type == "lock_screen":
            message = self.generate_message(state, reason)
            self.action_executor.send_notification("🧠 DevBuddy - Action Forte", message, duration=8)
            time.sleep(3)
            self.action_executor.lock_screen()
            return f"🔒 ÉCRAN VERROUILLÉ : {reason}"
        
        elif action_type == "force_sleep":
            self.action_executor.send_notification("🧠 DevBuddy - Action Critique", reason, duration=5)
            time.sleep(3)
            self.action_executor.force_sleep()
            return f"😴 MISE EN VEILLE : {reason}"
        
        return ""

# ============================================================
# AGENT PRINCIPAL
# ============================================================

class DevBuddyService:
    """Service principal de l'agent"""
    
    def __init__(self):
        self.sensor = EnvironmentSensor()
        self.brain = AgentBrain()
        self.is_running = False
        
    def save_current_state(self, state: DevState):
        with open(SHARED_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(asdict(state), f, indent=2, ensure_ascii=False)
    
    def log_action(self, entry: dict):
        if INTERVENTION_LOG_FILE.exists():
            with open(INTERVENTION_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []
        
        logs.append(entry)
        logs = logs[-30:]
        
        with open(INTERVENTION_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
    
    def scan_and_act(self):
        state = self.sensor.get_current_state()
        action_type, reason = self.brain.decide_action(state)
        action_message = self.brain.execute_action(state, action_type, reason)
        
        state.action_taken = action_type
        state.last_intervention = action_message
        
        if action_type != "none":
            log_entry = {
                "timestamp": state.timestamp,
                "action": action_type,
                "reason": reason,
                "message": action_message,
                "consecutive_minutes": state.consecutive_work_minutes,
                "hour": state.hour_of_day
            }
            self.log_action(log_entry)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ ACTION: {action_type.upper()} | {reason}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 👀 Surveillance | "
                  f"Travail: {state.consecutive_work_minutes}min | "
                  f"{state.hour_of_day}h | {state.active_window[:30]}...")
        
        self.save_current_state(state)
        return state, action_type
    
    def run(self, interval_seconds: int = 60):
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    🧠 DEVBUDDY AGENT v2.1                    ║
╠══════════════════════════════════════════════════════════════╣
║  TEST_MODE : {TEST_MODE:<47}║
║  Heure simulée : {SIMULATED_HOUR:02d}:{SIMULATED_MINUTE:02d}{' ' * 41}║
╠══════════════════════════════════════════════════════════════╣
║  Règles nocturnes :                                          ║
║  🟡 21h → Fermeture apps pro                                 ║
║  🟠 23h → Verrouillage écran                                 ║
║  🔴 01h → Mise en veille                                     ║
╠══════════════════════════════════════════════════════════════╣
║  Scan toutes les {interval_seconds} secondes{' ' * 41}║
║  Ctrl+C pour arrêter                                         ║
╚══════════════════════════════════════════════════════════════╝
""")
        
        self.is_running = True
        
        while self.is_running:
            try:
                self.scan_and_act()
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"  ❌ Erreur: {e}")
                time.sleep(interval_seconds)
        
        state = self.sensor.get_current_state()
        state.agent_running = False
        self.save_current_state(state)
        print("\n🛑 Agent arrêté. À bientôt !")

# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    print("🚀 Démarrage de DevBuddy Agent...")
    print(f"📁 Fichier system prompt : {SYSTEM_PROMPT_FILE.absolute()}")
    print(f"📁 Fichier logs : {INTERVENTION_LOG_FILE.absolute()}")
    
    if TEST_MODE:
        print(f"🧪 MODE TEST ACTIVÉ - Heure simulée : {SIMULATED_HOUR:02d}:{SIMULATED_MINUTE:02d}")
    print()
    
    service = DevBuddyService()
    service.run(interval_seconds=60)