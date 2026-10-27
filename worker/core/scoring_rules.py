# worker/core/scoring_rules.py
# Puente de compatibilidad modular para resolver las constantes sin duplicar código
try:
    from config.scoring_rules import *  # noqa: F401, F403
except (ImportError, ValueError):
    from worker.config.scoring_rules import *  # noqa: F401, F403
