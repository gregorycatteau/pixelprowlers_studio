import openai
from ai_assistants.models import AgentImpactReport, JaredLog
from django.utils.timezone import now


# ✅ Fonction principale appelée par chaque agent pour analyser l'impact
def analyze_message_impact(agent, message_log):
    """
    Analyse l'impact d’un message partagé sur l’agent spécifié.
    Génère automatiquement un AgentImpactReport et notifie Jared si nécessaire.
    """
    prompt = f"""
Tu es {agent.name}, un agent IA dans l'écosystème PixelProwlers.
Voici un message partagé que tu viens de recevoir :

---
{message_log.message}
---

Ta mission est de :
1. Évaluer si ce message impacte tes tâches, dépendances ou objectifs.
2. Décrire brièvement l’impact potentiel.
3. Classer cet impact selon l'échelle suivante : none, low, medium, high, critical.

Retourne uniquement une réponse structurée comme ceci (JSON brut sans explication) :

{{
  "impact_level": "...",
  "summary": "..."
}}
    """

    try:
        # Lancer l'appel OpenAI
        response = openai.ChatCompletion.create(
            model=agent.model,
            messages=[
                {"role": "system", "content": agent.instructions},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        raw = response["choices"][0]["message"]["content"]

        # Parser le JSON brut renvoyé par l’agent
        import json

        result = json.loads(raw)

        # Créer le rapport d’impact
        impact_report = AgentImpactReport.objects.create(
            agent=agent,
            message=message_log,
            impact_level=result["impact_level"],
            summary=result["summary"],
            alert_jared=(result["impact_level"] in ["high", "critical"]),
        )

        # Si impact critique → alerter Jared
        if impact_report.alert_jared:
            JaredLog.objects.create(
                horodatage=now(),
                agent_cible=agent.name,
                message=f"⚠️ Alerte impact critique sur {agent.name} suite à un message partagé.",
                reponse=impact_report.summary,
                statut="alert",
                priorite="critical",
                tags="impact,alert,auto",
            )

        return impact_report

    except Exception as e:
        # Logging d’erreur simplifié
        print(f"[ImpactAnalyzer] Erreur d’analyse pour {agent.name} : {e}")
        return None
