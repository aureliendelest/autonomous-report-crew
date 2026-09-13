import streamlit as st

from src.orchestrator import run_pipeline
from src.prompts import list_domains

st.title("Autonomous Report Crew")

domain = st.selectbox("Domaine", list_domains())
topic = st.text_input("Sujet", placeholder="ex : Olympique de Marseille")
generate = st.button("Générer le rapport", type="primary")

if generate:
    if not topic.strip():
        st.error("Merci de renseigner un sujet.")
    else:
        try:
            with st.status("Génération du rapport...", expanded=True) as status:
                report_path = run_pipeline(topic, domain, on_step=status.write)
                status.update(label="Rapport généré", state="complete")

            report_text = report_path.read_text(encoding="utf-8")
            st.markdown(report_text)
            st.download_button(
                "Télécharger le rapport (.md)",
                data=report_text,
                file_name=report_path.name,
                mime="text/markdown",
            )
        except RuntimeError as e:
            st.error(f"Erreur : {e}")
